"""**확산(diffusion)** -- 이야기의 농도를 재서 옅어지는 것을 막는다.

2026-09-04 실측 평:

    "이야기가 갈 수록 농도가 얕아져. 점층법으로 점점 점층되면서 이전의 발산된 형태를
     계속 증폭시켜가면서 더 넓게 퍼뜨려야 하는데, 계속 상황 설명, 디테일도 부족해.
     이전에 나왔던 소품들이 계속 점층되야해."

**왜 옅어졌는지는 구조에 있었다.** 다음 덩어리에게 넘어가는 것은 꼬리 900자뿐이다. 세
덩어리 앞에 나온 지포 라이터도, 양조장 뒤편의 개도, 그때 스쳐 간 우체부도 창 밖으로
빠진다. 원장(ledger)에 적혀는 있었지만 프롬프트에서 그것의 쓰임은 **"여기 적힌 것과
어긋나게 쓰지 마라"** -- 금지 목록이었다. 세계가 자산이 아니라 제약으로만 실려 있었으니
모델은 매번 새 방에서 새로 시작했고, 그래서 뒤로 갈수록 얕아졌다.

여기서는 원장을 뒤집어 **연료로 쓴다.** 두 가지를 센다:

  · **새로 는 것**(new)  -- 이 덩어리가 세계에 더한 고유명·사물·사실의 수
  · **되돌아온 것**(back) -- 앞에서 나왔다가 이 덩어리에서 다시 만져진 소품의 수

확산은 이 둘이 **함께** 있을 때만 일어난다. 새것만 있으면 산만해지고(연결 없는 나열),
되돌아온 것만 있으면 제자리를 돈다. 둘 다 바닥나면 그것이 "농도가 얕아졌다" 는 상태다.

대사도 여기서 잰다. "대사도 스토리의 일부야. 스토리만 있으니깐 재미없잖아. 단문의
대화도 있고 장문의 대화도 있어야해." -- 그래서 대사의 **길이 분포**를 본다.

리듬(rhythm.py)과 같은 규율을 따른다. **재서 숫자를 돌려주되, 원고를 죽이지 않는다.**
"게이트 크게 걸지마" 가 이 모듈의 첫 번째 제약이다 -- 확산은 기각으로 만들어지지 않는다.
"""
from __future__ import annotations

import hashlib
import os
import re

_QUOTE = re.compile(r"[\"“'']")

# 대사의 길이. 짧은 것과 긴 것이 **둘 다** 있어야 대화가 리듬을 갖는다.
TALK_SHORT = 20
TALK_LONG = 55
# **진짜 긴 대사.** 55자는 두 문장이면 넘는다 -- 그걸로는 "누가 길게 떠들었다" 가 안 된다.
# 실측 2026-09-05: "긴 대사가 없고 다들 너무 짧다." 한 덩어리에 이만한 것이 하나는 있어야
# 한 사람이 자기 얘기에 빠져 있는 대목이 생긴다.
TALK_HUGE = 120
# **대사 줄의 이만큼은 긴 대사다.** 글자 몫(bulk)만 재면 아주 긴 것 하나로 몫을 채우고
# 나머지를 전부 짧게 써도 통과한다 -- 그래서 대사가 문장처럼 짧아졌다. 이건 줄 수로 잰다.
# 기본은 길게 말하는 것이고, 짧게 끊는 것은 앞말에 기대는 한 마디일 때뿐이다.
# **목표치를 고정하지 않는다.** 하한을 하나 박아 두면 모델은 그 하한을 정확히, 그리고
# 매번 맞춘다 -- 그러면 그 자체가 주기가 된다(짧은 '-다' 에서 이미 겪었다). 덩어리마다
# 목표를 다시 뽑는다: 어떤 대목은 여덟 할이 길고, 어떤 대목은 둘만 길다. 씨앗에 묶여
# 있어 이어 쓰기에도 같은 값이 나온다.
LONG_LO = float(os.environ.get("DRIFT_TALK_LONG_LO", "0.20"))
LONG_HI = float(os.environ.get("DRIFT_TALK_LONG_HI", "0.85"))
LONG_SLACK = float(os.environ.get("DRIFT_TALK_LONG_SLACK", "0.15"))
LOOK = int(os.environ.get("DRIFT_TALK_LOOK", "2"))   # 앞 이만큼이 같은 쪽이면 뒤집는다
TSPREAD_MIN = float(os.environ.get("DRIFT_TALK_SPREAD", "0.45"))


def long_share(seed: str, n: int) -> float:
    """이 덩어리에서 **긴 대사가 차지할 몫**. 덩어리마다 다르다 -- 어떤 대목은 여덟 할이
    길고 어떤 대목은 둘만 길다. 흔들리는 목표치의 셈은 rhythm.wave 한 벌을 같이 쓴다
    (서술문 쪽에도 같은 장치가 필요해져서, 두 벌로 두지 않고 한 벌을 나눠 쓴다)."""
    from novel import rhythm
    return rhythm.wave(f"{seed}|talklong", n, LONG_LO, LONG_HI, LOOK)
TALK_MIN = 5             # 대사가 이만큼은 있어야 몫을 따진다

# **회수는 반복이 아니다.** 회수를 "앞에서 나온 이름을 다시 쓰기" 로만 재면, 가장 싸게
# 만족시키는 길이 같은 이름을 또 적는 것이 된다. 실측(2026-09-04): 한 덩어리에
# '1982년형 볼보' 4회, '삼십 년 전' 4회, '주머니' 5회. 그동안 볼보는 아무것도 하지
# 않는다 -- 처음부터 끝까지 헤드라이트를 깜빡이며 서 있다.
ECHO_MAX = 3

# **사람과 장소는 다르다.** 이 상한은 소품을 겨냥한 것이었다(한 덩어리에 '1982년형 볼보'
# 4회). 그런데 인물 이름과 무대가 되는 장소에도 걸렸고, 1,400자 안에서 주인공을 두 번만
# 부르는 것은 한국어로 불가능하다. 실측 2026-09-05: "도영 5회 · 웅포 4회" 로 기각되어
# 매 덩어리가 재시도를 다 쓰고, 그만큼 호출과 토큰이 네 배가 되어 429 를 불렀다.
#
# 사람은 부르라고 있는 이름이다. 장소도 그 안에서 이야기가 도는 동안은 계속 불린다.
# 그래서 상한을 따로 두고, **분량에 비례**시킨다 -- 3,000자짜리 덩어리에 2회는 억지다.
PEOPLE_ECHO = 6
PLACE_ECHO = 5
ECHO_PER = 500          # 이만큼 글자마다 상한을 하나씩 더 준다

# 연도·상표를 대라고 했더니 명사마다 접두사가 붙었다(실측: 한 덩어리에 연도 표기 9개 --
# 1982년형 볼보 · 1978년산 판화집 · 덴마크산 보드카). **구체성은 명사를 꾸미는 것이
# 아니라 그것이 무엇을 하는가에서 나온다.** 그래서 라벨에 상한을 둔다.
LABEL_MAX = 3
_YEAR = __import__("re").compile(r"\d{4}\s*년|\d{2}\s*년대")

LIMITS = {
    "new":   3,     # 이 덩어리가 세계에 더해야 하는 최소한의 새 고유물
    "back":  2,     # 앞에서 나온 소품 중 다시 만져야 하는 최소한의 수
    "long":  2,     # 긴 대사(설명·변명·수다·헛소리)가 적어도 둘
    "short": 2,     # 짧은 대사(끊고 받아치는 것)가 적어도 둘
    "bulk":  0.45,  # 대사 글자 수의 이만큼은 긴 대사여야 한다. **길이 몫(MIX)이 주된
                    # 자이고 이것은 바닥이다** -- 둘을 다 높이면 서로 다른 말을 한다.
    "srun":  2,     # 짧은 대사가 내리 이만큼까지. 넘으면 받아치는 게 아니라 딸꾹질이다
    "rally": 6,     # **한 번은 이만큼 주고받아야 한다** -- 대화가 이어진다는 것의 정의
    "huge": 1,      # 아주 긴 대사(120자+)가 적어도 하나
    "grow":  1,     # **앞엣것에서 자라난 새 이름이 적어도 하나**
    "owed": 9,      # 열린 것이 이보다 많은데 하나도 안 닫으면 나열이 된다
}

# 점층의 자국은 이름에 남는다. 사용자가 든 예: 웅포 → **웅포 소금 공장**. 앞에서 지어낸
# 이름이 다음 덩어리에서 더 구체적인 것으로 자란다 -- 그것이 세계가 깊어졌다는 증거다.
# 회수(back)만 재면 "웅포에 다시 갔다" 로도 채워지는데, 그건 다시 부른 것이지 자란 것이
# 아니다(실측 2026-09-05: "점층이 약하다. 전작이 웅포 → 웅포 소금 공장이었던 것에 비해").

# 개수도 몫도 채웠는데 "대화가 길게 이어지지 않는다" 는 평이 나왔다(실측 2026-09-05).
# 재보니 대사가 한 줄씩 흩어져 있었다 -- 서술 사이에 한 마디, 또 한참 뒤에 한 마디.
# **대화는 대사의 양이 아니라 연달아 오가는 길이다.** 그래서 가장 긴 연속 구간을 센다.

# 왜 몫까지 재는가. 개수 하한만 두었더니 모델이 최소로 맞췄다 -- 긴 대사 딱 하나에
# 짧은 대사 열 개. 그러면 자는 통과하는데 읽으면 대사가 죄다 짧다(실측 2026-09-05:
# "대사가 왜 짧아졌지"). 개수는 하한을 지키는 데 쓰고, **비중은 몫으로 잡는다.**

# 원장에서 소품으로 세는 칸. 시간(time)은 이름이 아니라 서술이라 뺀다.
BUCKETS = ("people", "places", "objects", "facts")


def props(ledger: dict) -> list[str]:
    """지금까지 세계에 놓인 것들의 이름."""
    out = []
    for b in BUCKETS:
        out.extend(str(k) for k in (ledger.get(b) or {}))
    return out


def added(before: dict, after: dict) -> list[str]:
    """이 덩어리가 새로 놓은 것들."""
    old = set(props(before))
    return [p for p in props(after) if p not in old]


def touched(text: str, names: list[str]) -> list[str]:
    """본문이 실제로 만진 이름들. 원장에 적혀 있는 것과 글에 나온 것은 다르다."""
    return [n for n in dict.fromkeys(names) if len(n) >= 2 and n in text]


# 식은 소품으로 되올릴 수 있는 나이. 이보다 오래된 것은 연료로 쓰지 않는다.
#
# **처음엔 나이를 안 봤다. 그래서 원고가 첫 장면으로 되돌아갔다**(실측 2026-09-05: "새로
# 쓴 글이 내가 처음에 제시해준 첫 문장으로 되돌아갔어"). 원인은 이렇다 -- 첫 문장에 나온
# 것들(보잉 747, 함부르크 공항)은 한번 원장에 오르면 영원히 "최근 글에 없는 것" 이라서,
# 매 덩어리마다 "이번에 다시 만질 것" 으로 다시 올라갔다. 회수하라고 시켰으니 모델은
# 성실하게 공항으로 돌아갔다.
#
# 회수는 **가까운 과거**를 향해야 한다. 세 덩어리 전에 놓인 라이터를 다시 꺼내는 것은
# 점층이지만, 마흔 덩어리 전의 공항으로 돌아가는 것은 역행이다.
FUEL_AGE = 8


def cold(ledger: dict, recent: str, now: int = 0, keep: int = 12) -> list[str]:
    """**식은 소품** -- 최근 글에는 없지만 **아직 오래되지 않은** 것. 확산의 연료다.

    나이를 모르는 원장(옛 원고)은 나이를 안 따진다 -- 그때는 이 문제가 없었던 것이 아니라
    잴 수가 없는 것이라, 없는 것으로 치고 예전처럼 군다.
    """
    age = ledger.get("_age") or {}
    out = []
    for p in props(ledger):
        if len(p) < 2 or p in recent:
            continue
        born = age.get(p)
        if born is not None and now - born > FUEL_AGE:
            continue                      # 너무 오래됐다 -- 여기로 돌아가면 역행이다
        out.append(p)
    return out[-keep:]


def talk(text: str) -> tuple[int, int]:
    """대사줄을 짧은 것과 긴 것으로 나눠 센다."""
    short, long, _ = _talk3(text)
    return short, long


def _talk3(text: str) -> tuple[int, int, float]:
    short, long, bulk = _talk4(text)[:3]
    return short, long, bulk


def talk_spread(text: str) -> float:
    """대사 길이의 퍼짐. 다 비슷하면 주고받기가 아니라 낭독이다."""
    from novel import rhythm
    lens = [len(l.strip()) for l in text.splitlines()
            if l.strip() and _QUOTE.match(l.strip())]
    return rhythm.spread(lens)


def _talk4(text: str) -> tuple:
    """짧은 것 · 긴 것 · 긴 대사의 몫 · **가장 길게 주고받은 턴 수** ·
    짧은 대사가 내리 이어진 최대 · 짧은 대사의 몫.

    마지막 것이 '대화가 이어진다' 는 말의 정의다. 대사 사이에 짧은 지문("그는 웃었다")이
    한 줄 끼는 것은 대화를 끊지 않는다 -- 사람은 말하면서 움직이니까. 그러나 서술이
    두 줄 이상 이어지면 대화는 거기서 끝난 것이다.
    """
    short = long = mid = talks = 0
    long_chars = all_chars = 0
    rally = best = gap = 0
    srun = sbest = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _QUOTE.match(line):
            all_chars += len(line)
            if len(line) >= TALK_LONG:
                long += 1
                long_chars += len(line)
                srun = 0
            elif len(line) <= TALK_SHORT:
                short += 1
                srun += 1
                sbest = max(sbest, srun)
            else:
                mid += 1
                srun = 0
            talks += 1
            rally += 1
            gap = 0
            best = max(best, rally)
        else:
            gap += 1
            if gap >= 2 or len(line) > 120:   # 서술이 길거나 두 줄 이어지면 대화가 끊긴다
                rally = 0
    return (short, long, (long_chars / all_chars if all_chars else 0.0), best,
            sbest, (long, mid, short))


def overused(text: str, names: list[str], ledger: dict | None = None
             ) -> list[tuple[str, int]]:
    """한 덩어리에서 **너무 자주 불린 이름**. 회수가 반복으로 변질된 자리다.

    사람·장소·소품에 각각 다른 상한을 준다. 소품을 네 번 부르면 반복이지만 사람을 네 번
    부르는 것은 그냥 대화다.
    """
    ledger = ledger or {}
    people = set(ledger.get("people") or {})
    places = set(ledger.get("places") or {})
    bonus = max(0, len(text) // ECHO_PER - 1)
    out = []
    for n in dict.fromkeys(names):
        if len(n) < 2:
            continue
        cap = (PEOPLE_ECHO if n in people else
               PLACE_ECHO if n in places else ECHO_MAX) + bonus
        c = text.count(n)
        if c > cap:
            out.append((n, c))
    return sorted(out, key=lambda kv: -kv[1])


def labels(text: str) -> int:
    """연도 표기의 수. 이것이 많다는 것은 구체성이 장식이 됐다는 뜻이다."""
    return len(_YEAR.findall(text))


def grown(before: dict, after: dict) -> list[str]:
    """**앞엣것에서 자라난 이름.** 옛 이름을 품은 새 이름이면 그것이 점층의 자국이다."""
    old = [p for p in props(before) if len(p) >= 2]
    out = []
    for new in added(before, after):
        if any(o in new and o != new for o in old):
            out.append(new)
    return out


def opened(before: dict, after: dict) -> tuple[int, int]:
    """이 덩어리가 **연 것과 닫은 것**. 증명은 미결을 만들고 또 갚으면서 나아간다.

    벌리기만 하면 산만해지고, 닫기만 하면 이야기가 마른다. 그래서 둘 다 센다.
    """
    b = set((before.get("open") or {}))
    a = set((after.get("open") or {}))
    return len(a - b), len(b - a)


# 앞엣것이 **도구로 쓰인 자국**. 증명에서 보조정리는 언급되는 것이 아니라 쓰인다 --
# 라이터가 다시 나오는 것과 라이터로 자물쇠를 지지는 것은 다르다.
#
# 한국어에서 그 자국은 조사에 남는다: "지포로 …", "그 종이를 써서 …". 완벽한 판정은
# 아니지만(비유에도 '로' 가 붙는다) **재서 돌려주기만 하는 소프트한 자**라 그걸로 족하다.
_MEANS = ("로 ", "으로 ", "를 써", "을 써", "를 들고", "을 들고", "로써", "를 가지고",
          "을 가지고", "에 대고", "로 삼", "으로 삼")


def tooled(text: str, names: list[str]) -> list[str]:
    """앞에서 나온 것 중 이번에 **수단이 된** 것들."""
    out = []
    for n in dict.fromkeys(names):
        if len(n) < 2:
            continue
        i = text.find(n)
        while i >= 0:
            after = text[i + len(n):i + len(n) + 6]
            if any(after.startswith(m.strip()) or after.startswith(m) for m in _MEANS):
                out.append(n)
                break
            i = text.find(n, i + 1)
    return out


def measure(text: str, before: dict, after: dict) -> dict:
    short, long, bulk, rally, srun, mix = _talk4(text)
    huge = sum(1 for l in text.splitlines()
               if l.strip() and _QUOTE.match(l.strip()) and len(l.strip()) >= TALK_HUGE)
    new_open, closed = opened(before, after)
    return {"rally": rally, "huge": huge, "tspread": talk_spread(text),
            "grow": grown(before, after),
            "tool": tooled(text, props(before)),
            "opened": new_open, "closed": closed,
            "owed": len(after.get("open") or {}), "new": len(added(before, after)),
            "back": len(touched(text, props(before))),
            "short": short, "long": long, "bulk": bulk,
            "srun": srun, "mix": mix,
            "over": overused(text, props(before) + props(after), after),
            "labels": labels(text)}


def check(text: str, before: dict, after: dict, now: int = 0,
          want: float | None = None, tune: dict | None = None) -> list[str]:
    """옅어진 자리만 사람 말로 돌려준다."""
    m = measure(text, before, after)
    # **자를 갈래가 조절한다.** 대사 관련 자(주고받기 · 긴 대사 · 아주 긴 대사)는
    # 갈래 가정이었다 -- 서술이 이야기를 끄는 갈래에서는 상대가 아예 없는 대목이
    # 흔한데, 그것을 벌하면 좋은 글이 낙제한다(실측: 직장물 표본이 여덟 군데 걸렸다).
    lim = dict(LIMITS)
    lim.update((tune or {}).get("자", {}))

    old = props(before)
    out = []

    if m["new"] < lim["new"]:
        out.append(f"이 덩어리가 세계에 더한 것이 {m['new']}개뿐이다. "
                   f"{LIMITS['new']}개는 넘겨라 -- 새 사람, 새 장소, 새 물건, 새 사실. "
                   f"**이름을 붙이고, 그것이 무언가를 하게 해라.** 설명만 하지 말고 세계를 늘려라")

    # 되돌아옴은 **되돌아올 것이 쌓인 뒤에만** 따진다. 첫 덩어리에 회수를 요구할 수는 없다.
    if len(old) >= 4 and m["back"] < lim["back"]:
        fuel = cold(before, text, now)
        out.append(f"앞에서 나온 것 중 이 덩어리가 다시 만진 것이 {m['back']}개뿐이다. "
                   f"{LIMITS['back']}개는 다시 만져라 -- 그런데 **똑같이 쓰지 말고 한 단계 "
                   f"키워라.** 그때 그냥 놓여 있던 물건이 이번엔 쓰이거나, 망가지거나, "
                   f"다른 사람 손에 있거나, 그것 때문에 일이 생긴다"
                   + (f". 식은 것들: {' · '.join(fuel[:8])}" if fuel else ""))

    if m["over"]:
        worst = " · ".join(f"{n} {c}회" for n, c in m["over"][:4])
        out.append(f"같은 이름을 너무 자주 불렀다 -- {worst}. "
                   f"**회수는 다시 부르는 것이 아니라 다시 쓰는 것이다.** 이름을 또 적는 대신 "
                   f"그것이 무언가를 하게 해라 -- 쓰이거나, 망가지거나, 손이 바뀌거나, "
                   f"그것 때문에 일이 생기거나. 두 번째부터는 '그것', '차', '그 종이' 로 받아라")

    if m["labels"] > LABEL_MAX:
        out.append(f"연도·연식 표기가 {m['labels']}개다. {LABEL_MAX}개까지다 -- "
                   f"'1982년형 볼보', '1978년산 판화집' 처럼 명사마다 접두사를 붙이지 마라. "
                   f"**구체성은 명사를 꾸미는 것이 아니라 그것이 무엇을 하는가에서 나온다.** "
                   f"연식이 중요하면 누가 그걸 입에 올리게 해라")

    if m["long"] < lim["long"]:
        out.append(f"{TALK_LONG}자 넘는 긴 대사가 {m['long']}개다. 적어도 {LIMITS['long']}개는 "
                   f"넣어라 -- 누가 길게 떠들어야 한다. 변명이든 수다든 아무도 안 "
                   f"물어본 내력이든. **대사로 이야기를 진행시켜라.** 상황 설명으로 넘기지 마라")

    if m["long"] and m["bulk"] < lim["bulk"]:
        out.append(f"대사 글자의 {m['bulk']:.0%}만 긴 대사다. {LIMITS['bulk']:.0%}는 넘겨라 -- "
                   f"짧게 받아치는 말만 이어지면 핑퐁이 아니라 딸꾹질이다. **한 사람이 한 번은 "
                   f"길게, 문장을 몇 개씩 이어서, 자기가 자기 말을 고쳐 가며 말해야 한다.** "
                   f"긴 대사 안에서도 점층해라 -- 좁히거나, 키우거나, 뒤집어라")

    if len(old) >= 3 and len(m["grow"]) < lim["grow"]:
        seeds = [p for p in cold(before, "", now)][-6:]
        out.append("**앞에서 지어낸 이름 하나를 더 구체적인 것으로 키워라.** 그냥 다시 "
                   "부르는 것은 회수지 점층이 아니다 -- 그 이름을 품은 새 이름이 나와야 한다. "
                   "장소면 그 안의 건물이나 구역, 사람이면 그가 속한 것, 물건이면 그 부분이나 "
                   "출처. 그렇게 자란 것에 다시 사정을 하나 붙여라"
                   + (f". 키울 만한 것: {' · '.join(seeds)}" if seeds else ""))

    # **닫는 것 없이 열기만 하면 나열이다.** 다만 무르게 본다 -- 미결이 쌓여 있어도
    # 되는 이야기가 있고, 닫는 자리는 사람이 정하는 것이다.
    if m["owed"] > lim["owed"] and not m["closed"]:
        out.append(f"열린 것이 {m['owed']}개인데 이번에 닫은 것이 없다. "
                   f"{LIMITS['owed']}개를 넘으면 그건 이야기가 아니라 목록이다 -- **하나는 "
                   f"닫아라.** 시원한 답일 필요는 없다. 김빠지는 답도, 틀린 답도, 아무도 "
                   f"확인 못 하는 답도 답이다")

    # 회수는 셋인데 하나도 안 쓰였으면, 다시 부르기만 한 것이다.
    if len(old) >= 4 and m["back"] >= lim["back"] and not m["tool"]:
        out.append("앞엣것을 다시 만지기는 했는데 **쓰지는 않았다.** 하나는 수단이 되게 "
                   "해라 -- 그것으로 무엇을 하거나, 그것 때문에 무엇이 되거나, 그것을 "
                   "주고 무엇을 받거나. 언급은 회수가 아니다")

    if m["rally"] < lim["rally"]:
        out.append(f"제일 길게 주고받은 대화가 {m['rally']}턴이다. 한 번은 {LIMITS['rally']}턴을 "
                   f"넘겨라 -- **대사와 대사를 붙여 놓아라.** 서술 사이에 한 마디씩 흩어 놓으면 "
                   f"그건 대화가 아니라 인용이다. 한 사람이 물으면 다른 사람이 답하고, 그 답을 "
                   f"받아 또 묻고, 딴소리가 끼고, 그러다 원래 얘기로 돌아온다")

    if m["long"] and m["huge"] < lim["huge"]:
        out.append(f"{TALK_HUGE}자 넘는 대사가 {m['huge']}개다. 하나는 있어야 한다 -- "
                   f"**한 사람이 자기 얘기에 빠져서 길게 떠드는 대목.** 아무도 안 물어본 "
                   f"내력이든, 변명이든, 틀린 지식이든. 그 안에서 스스로 말을 고치고, "
                   f"딴 데로 샜다가, 돌아온다")

    # **0.6 이었는데 8할을 길게 쓰라는 자와 부딪쳤다.** 대사 줄의 여덟 할이 55자를
    # 넘으면 길이는 자연히 모인다 -- 그 상태를 "다 비슷하다" 고 벌하면 두 자가 서로
    # 다른 말을 하는 것이다. 이제 퍼짐은 **긴 것들끼리 얼마나 다른가**를 본다.
    if m["long"] >= 2 and m["tspread"] < TSPREAD_MIN:
        out.append(f"대사 길이가 다 비슷하다(퍼짐 {m['tspread']:.2f}). 두 마디짜리와 "
                   f"열 줄짜리가 **같은 장면 안에** 있어야 한다 -- 다 고르면 주고받기가 "
                   f"아니라 낭독이다")

    if m["short"] < lim["short"]:
        out.append(f"{TALK_SHORT}자 이하 짧은 대사가 {m['short']}개다. {LIMITS['short']}개는 "
                   f"넘겨라 -- 끊고, 받아치고, 딴소리하는 짧은 말이 긴 대사 사이에 있어야 한다")

    # **짧은 것은 받아칠 때만이다.** 아래 둘이 "기본은 길게" 를 지키는 자다 -- bulk 만
    # 두면 긴 대사 하나로 몫을 채우고 나머지를 전부 짧게 써도 통과한다.
    if m["srun"] > lim["srun"]:
        out.append(f"짧은 대사가 내리 {m['srun']}번 이어진 자리가 있다. "
                   f"{LIMITS['srun']}번을 넘기지 마라 -- 짧게 받아치는 것은 **앞말에 기대는 "
                   f"한 마디**일 때뿐이고, 그것이 이어지면 주고받기가 아니라 딸꾹질이다")
    mix = m.get("mix")
    if mix and sum(mix) >= TALK_MIN and want is not None:
        share = mix[0] / sum(mix)
        if share < want - LONG_SLACK:
            out.append(f"대사 줄의 {share:.0%}만 {TALK_LONG}자를 넘는다. **이 대목은 "
                       f"{want:.0%}**다 -- 할 말이 있으면 다 하고, 딴 얘기로 새고, 묻지 "
                       f"않은 것까지 말한다. 짧게 끊는 것은 앞사람 말을 받아칠 때만이다")
        elif share > want + LONG_SLACK and want <= 0.5:
            out.append(f"대사 줄의 {share:.0%}가 {TALK_LONG}자를 넘는다. **이 대목은 "
                       f"{want:.0%}**다 -- 여기서는 짧게 주고받아라. 매 대목을 길게 쓰면 "
                       f"그것도 한 가지 가락이다")
    return out


def score(text: str, before: dict, after: dict) -> float:
    """옅은 정도. 낮을수록 짙다."""
    m = measure(text, before, after)
    s = max(0, LIMITS["new"] - m["new"]) * 0.2
    if len(props(before)) >= 4:
        s += max(0, LIMITS["back"] - m["back"]) * 0.2
    s += sum(c - ECHO_MAX for _, c in m["over"]) * 0.05
    s += max(0, m["labels"] - LABEL_MAX) * 0.05
    s += max(0, LIMITS["long"] - m["long"]) * 0.15
    s += max(0.0, LIMITS["bulk"] - m["bulk"]) * 0.3
    s += max(0, LIMITS["rally"] - m["rally"]) * 0.08
    s += max(0, LIMITS["huge"] - m["huge"]) * 0.2
    s += max(0, LIMITS["grow"] - len(m["grow"])) * 0.25
    if len(props(before)) >= 4 and m["back"] >= LIMITS["back"] and not m["tool"]:
        s += 0.15
    if m["owed"] > LIMITS["owed"] and not m["closed"]:
        s += 0.2
    s += max(0, LIMITS["short"] - m["short"]) * 0.1
    return s
