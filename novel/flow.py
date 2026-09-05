"""연속 집필 -- **조립하지 않는다. 한 문장에서 이어 쓴다.**

지금까지는 결말을 먼저 정하고 거꾸로 비트를 쌓았다(episode.py). 그 방식은 인과가 튼튼한
대신 문장이 칸에 갇힌다 -- 씬마다 분량이 할당되고, 회차마다 구조가 요구되고, 관문 아홉이
매번 판정한다. 그렇게 나온 원고가 무겁고 단조로웠다(2026-09-04 사용자 평).

여기서는 반대로 간다:

  · **줄거리를 먼저 짜지 않는다.** 첫 문장 하나에서 다음이 파생되고, 그 다음이 또 파생된다
  · **조립하지 않는다.** 씬도 회차도 없다. 덩어리(chunk)를 이어 붙인다
  · **관문을 끈다.** 남기는 것은 **모순 하나**뿐이다 -- 앞에서 쓴 것과 어긋나는가
  · 어휘도 사건도 자유다. 조건에 맞지 않아도 상관없다

모순만 남기는 이유. 자유롭게 쓰라고 하면 모델은 세 덩어리 뒤에 인물 이름을 바꾸고, 죽은
사람을 걷게 하고, 겨울이던 계절을 여름으로 만든다. 그것만은 코드가 잡아야 한다 -- 취향은
사람이 보면 되지만 모순은 길어질수록 사람도 못 본다.

그래서 **세계를 JSON 원장으로 키운다.** 덩어리마다 추출기가 새로 확정된 것을 뽑아 원장에
더하고, 그때 원장과 부딪히는 것이 있으면 그 덩어리를 기각하고 다시 쓴다.

    python3 novel/flow.py --chars 6000 --out novel/flow.json
    python3 novel/flow.py --resume novel/flow.json --chars 12000   # 이어서
    python3 novel/flow.py --read novel/flow.json                   # 읽기
"""
from __future__ import annotations

import argparse
import difflib
import os
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from novel import drive as D                                          # noqa: E402
from novel import echo                                                # noqa: E402
from novel import doubt                                               # noqa: E402
from novel import diffusion                                           # noqa: E402
from novel import bridge                                              # noqa: E402
from novel import bond                                                # noqa: E402
from novel import trait                                               # noqa: E402
from novel import matter                                              # noqa: E402
from novel import shock as SH                                         # noqa: E402
from novel import rhythm                                              # noqa: E402
from novel import wording                                             # noqa: E402
from novel import genre as GENRE                                      # noqa: E402
from novel import style                                               # noqa: E402

# 한 번에 받는 덩어리. 너무 크면 모델이 뒤로 갈수록 늘어지고, 너무 작으면 점층이 덩어리
# 경계에 잘린다. 1,200~1,500자가 문장론(점층 -> 전환)이 한 바퀴 도는 크기다.
# 인물 카드에 적는 것. **정하면 적어두고 다음부터 참조한다** -- 적어두지 않으면 모델은
# 세 덩어리 뒤에 다른 사람으로 만든다. 대사가 인물마다 달라지는 것도 이 카드에서 나온다:
# "거칠게" 는 한 인물의 특징이지 소설의 규칙이 아니다.
CARD = ("나이", "키", "몸", "속", "관계", "성격", "혈액형", "가족", "과거", "트라우마",
        "좋아하는 것", "싫어하는 것", "취미", "전공", "직업", "말투", "버릇", "겉모습")

# **게이트는 최소로 만든다.** 자유도가 이 모드의 전부다 -- 기각이 잦으면 그 자유가 죽는다.
#
# 그래서 모순을 따지는 자리를 이만큼으로 줄인다:
#   · **주요 인물**(두 덩어리 이상 나온 사람)의
#   · **핵심 칸**(나이 · 생사 · 가족 · 직업 · 이름)만.
#
# 나머지는 전부 **기록만 하고 기각하지 않는다** -- 주변 사물, 스쳐 간 인물, 장소 묘사,
# 잡다한 사실. 실측(VM): "은색의 불규칙한 소리를 내는 물건" 이 "1950년대 독일 잡화점에서
# 판매된 은색 모델" 로 자세해진 것을 기각했다. 그건 같은 라이터고, 그런 기각이 원고를
# 못 나오게 한다. 놓친 모순은 사람이 읽다 발견하지만 과잉 기각은 글 자체를 없앤다.
CORE = ("나이", "생사", "가족", "직업", "이름", "성별")
# 주요 인물의 조건 둘 -- **자주 나오고, 카드가 두툼하다.** 하나만 보면 스쳐 간 행인이
# 두 번 언급됐다고 주요 인물이 되고, 그 사람 나이가 바뀐 것으로 원고가 기각된다(실측).
# 소설이 실제로 붙잡고 가는 사람은 등장이 잦고 설정도 쌓인다.
MAIN_AFTER = 3        # 이만큼 덩어리에 나와야
MAIN_FIELDS = 3       # 그리고 카드에 이만큼 칸이 차야 주요 인물이다

# **숫자로 정해지는 칸만 엄격하게 본다.** 나머지는 묘사이고, 묘사는 뒤로 갈수록 자세해지는
# 것이 정상이다 -- 그것까지 모순으로 잡으면 두 번째 덩어리부터 진도가 안 나간다.
# 실측(2026-09-04 VM): "은색의 불규칙한 소리를 내는 물건" 이 "1950년대 초반 독일 잡화점에서
# 판매된 은색 모델" 로 자세해진 것을 모순으로 기각했다. 그건 같은 라이터다.
STRICT = ("나이", "키", "혈액형", "생일", "몸무게", "연도", "번호")
SIMILAR = 0.55

# 죽음을 가리키는 말. 이 칸만은 한 방향으로만 흐른다 -- 산 사람은 죽을 수 있고,
# 죽은 사람은 못 돌아온다.
_DEAD = re.compile(r"죽|사망|시신|시체|숨(을)?\s*거|고인|타계|없어졌다가 시신")        # 이만큼 닮았으면 같은 것을 더 자세히 말한 것으로 본다

# 한 번에 받는 분량. 모델의 한 번 출력 한도(8,192토큰 = 한글로 대략 8천 자)에 견주면
# 1,400자는 8분의 1이었다. 호출 한 번의 값은 분량에 거의 안 비례하므로(프롬프트가
# 18,000자인데 답이 1,400자였다), 작게 받는 것은 그 자체로 낭비다. 게이트는 분량과
# 무관하게 비율로 재므로 크게 받아도 잣대는 그대로 선다.
CHUNK = int(os.environ.get("DRIFT_CHUNK", "3200"))
# 한 번에 고쳐 달라고 보낼 문장 수의 상한. 너무 많이 보내면 되받은 것이 성의 없어지고,
# 프롬프트도 다시 커진다 -- 아끼려던 것이 도로 는다.
MEND_MAX = int(os.environ.get("DRIFT_MEND_MAX", "12"))
# 다시 쓰는 횟수. 모순·리듬·농도가 이 예산을 함께 쓴다. 둘이던 것을 셋으로 올렸다 --
# 재는 자가 늘었는데 예산이 그대로면 첫 지적만 고치고 끝난다.
# **표류 계수** -- 부조리의 세기. 1.0 이면 축을 전부 매번 켠다.
#
# 축을 넷이나 겹쳐 놓으니(확산 · 급발진 · 소재 · 사건) 뒤로 갈수록 부조리가 쌓였다.
# 사용자 평: "후반부로 갈 수록 조금 부조리가 심해져. drift 계수를 0.8로 해줘."
#
# 그래서 계수 하나로 셋을 함께 조인다 -- 급발진이 켜지는 비율, 소재의 갈래가 붙는 비율,
# 사건이 터지는 간격. 켜고 끄는 것은 해시라서 **이어 쓰기에도 같은 자리에서 같게** 나온다.
# 확산과 리듬은 건드리지 않는다. 그건 부조리가 아니라 문장의 문제다.
#
# 0.8 → 0.5 로 내렸다가 **1.0 으로 되돌렸다.** 계수를 낮춰서 밀도를 잡으려 했는데, 정작
# 밀도를 올린 것은 계수가 아니라 소재 축이었다(아래 MATTER). 급발진을 반으로 줄이니
# 밀도는 그대로인 채 인물만 밋밋해졌다 -- 원인이 아닌 것을 조인 셈이다.
#
# 그래서 급발진·사건은 매 덩어리 · 2,000자로 되돌리고, 소재 축을 끈다. 사용자 평이
# 가리킨 것이 그 배치였다: "매 덩어리 확산 + 급발진 1 / 2,000자마다 사건 -- 딱 이때가
# 제일 좋다."
DRIFT = 1.0

# 연결이 실리는 비율. 매번 이으면 세계가 음모론이 된다 -- 모든 것이 연결돼 있으면
# 아무것도 연결돼 있지 않은 것과 같다.
BRIDGE = 0.3
# 세워 둔 것의 지반을 흔드는 비율. 늘 의심하면 아무것도 안 믿기고, 그러면 흔들 것도 없다.
DOUBT = 0.3
# 시점을 옮기는 비율. 자주 옮기면 독자가 누구도 안 따라간다.
POV = 0.2

# 통칙을 깨는 비율. 늘 깨면 통칙이 아니고, 안 깨면 배경이다.
EXCEPTION = 0.3
# 이을 것이 이만큼 쌓이기 전에는 안 잇는다. 셋으로 다리를 놓으면 그냥 우연이다.
BRIDGE_AFTER = 6

# 관계가 실리는 비율. 매번 새 관계를 붙이면 인물이 관계표가 된다.
BOND = 0.4

# 설정(외현·내현)이 붙는 비율. 매 덩어리에 넣으면 소설이 인물 소개서가 된다.
TRAIT = 0.35

# **소재 축의 비율. 0 이면 끈다.**
#
# 갈래(총격전·던전·에일리언)와 매체(편지·노래·라디오)를 매 덩어리에 얹었더니 확산과
# 급발진 위에 셋이 더 쌓여 "너무 밀도가 높아졌다". 재료를 넓히려던 것이 재료를 들이붓는
# 것이 됐다. 껐다 -- 필요하면 --matter 0.3 처럼 조금만 켠다.
MATTER = 0.0

# 재시도 예산. 셋이었는데 다섯으로 올렸다 -- 자가 열여섯인데 예산이 셋이면 통과가
# 어려운 것이 아니라 **거의 불가능**하다. 다만 예산을 늘리는 것은 호출을 늘리는 것이라
# 자를 무르게 하는 쪽이 먼저다(2026-09-05: 인물 이름 상한이 진짜 병목이었다).
MAX_REWRITE = 5
# 나아지지 않는 재시도를 몇 번까지 봐줄 것인가. 되먹임이 한 건씩 돌아가므로 한 번은
# 봐준다(다음 항목에서 좋아질 수 있다). 두 번 연속 제자리면 그 덩어리는 더 시켜도
# 안 되는 것이고, 그때부터는 쿼터만 태운다 -- 어차피 제일 나은 후보를 채택한다.
GIVE_BACK = int(os.environ.get("DRIFT_GIVE_BACK", "2"))
# 다음 덩어리에 넘기는 꼬리. 900자였는데, 그러면 세 덩어리 앞의 소품이 창 밖으로 빠지고
# 점층이 매번 새로 시작한다(실측: "갈 수록 농도가 얕아져"). 식은 소품은 diffusion 이
# 이름으로 따로 올려주지만, 꼬리 자체도 한 뼘 늘려 둔다.
TAIL = 1200

# 첫 문장. **여기서 모든 것이 파생된다** -- 줄거리를 안 짜므로 이 몇 줄이 씨앗의 전부다.
# 좌표(나이·장소·자세)를 놓고, 배경을 하나의 그림으로 묶고, 마지막에 밖에서 안으로
# 넘어간다("아, 또 독일인가 하고 나는 생각했다"). style.py 의 [상황]/[전환] 이 말하는
# 것을 한 문단이 다 하고 있어서, 이 자리에 두면 다음 덩어리가 그 리듬을 이어받는다.
FIRST = (
    "내가 너에게 처음 함부루크에 관한 이야기를 던졌을 때, 너는 있지도 않는 "
    '가상의 도시 "웅포"를 꺼내들었지. 나는 네 이름도 몰라 성도 몰라 나이도 몰라 '
    "너에 대해 아는 것이 아무것도 없지만, 봐바 이렇게 두 쉼표 사이에 대사를 넣을 "
    "수도 있다고, 꼭 기억해, 웅포는 존재해.\n"
)



# 첫 덩어리에만 실린다. **내용을 지정하지 않는다** -- 예전엔 여기에 "양조장의 내력을
# 풀어라 / 크리스마스 이브다 / 오로라로 흘러라" 가 적혀 있었는데, 그건 그때 씨앗에 묶인
# 각본이었다. 첫 문장을 갈아 끼우면 그런 지시는 남의 이야기를 시키는 것이 된다.
#
# 그래서 **무엇을 쓸지가 아니라 어떻게 열지만** 말한다. 세계가 아직 비어 있어 확산 지시가
# 실리지 않는 유일한 덩어리이므로, 여기서 할 일은 딱 하나다 -- 다음 덩어리가 붙잡을
# 손잡이를 몇 개 만들어 두는 것.
OPENING = """[이 첫 덩어리가 할 일]
  * **첫 문장이 놓은 좌표에서 출발해라.** 거기 있는 것들(그 장소, 그 계절, 그 사물,
    화자의 나이)이 이야기의 재료다. 새 무대를 따로 차리지 마라.
  * **사람을 하나 만나게 해라.** 이름을 주고, 사정을 한 줄 주고, 말을 시켜라. 세계는
    사람에서 자란다.
  * **가짜를 진짜처럼 지어내라** -- 그 건물이 언제 지어졌는지, 왜 그렇게 불리는지,
    누가 거기 있었는지. 사전에 없는 것이라도 있는 것처럼 대라.
  * 사건을 만들려 애쓰지 마라. 첫 덩어리는 **손잡이를 만드는 자리**다 -- 다음 덩어리가
    다시 만질 사람 하나, 장소 하나, 물건 하나. 그걸로 충분하다.
  * 마지막은 닫지 마라. 문장 하나를 열어둔 채로 끊어라."""


# ---------------------------------------------------------------- 원장

def blank(first: str = FIRST) -> dict:
    # shocks: 지금까지 터진 사건의 수. 뽑기가 여기 묶여 있어 이어 쓰기에도 순서가 이어진다.
    # since: 마지막 사건 이후 쓴 글자 수.
    # words: 지어낸 낱말과 그 뜻. **기록만 하고 절대 기각하지 않는다** -- 다만 한 번 뜻을
    # 준 말은 계속 같은 뜻으로 쓰여야 해서 원장에 남긴다.
    # open: **던져지고 아직 안 닫힌 것.** 원장의 다른 칸이 전부 '확정된 사실' 인 데 비해
    # 여기만 미결이다. 증명이 흘러가는 느낌은 결론이 정해져서가 아니라 갚아야 할 것이
    # 쌓여 있어서 생긴다 -- 닫힌 사실만 적으면 매 덩어리가 자기 안에서 완결되고, 그러면
    # 표류가 아니라 나열이 된다.
    return {"first": first, "chunks": [], "shocks": 0, "since": 0, "drift": DRIFT,
            "genre": GENRE.DEFAULT,
            "matter": MATTER, "trait": TRAIT, "bond": BOND, "bridge": BRIDGE, "exception": EXCEPTION, "doubt": DOUBT, "pov": POV,
            "ledger": {
        "people": {}, "places": {}, "facts": {}, "time": [], "objects": {},
        "words": {}, "open": {}, "rules": {}, "macguffin": {}, "_folded": []}}


def _merge(ledger: dict, delta: dict, at: int = 0) -> list:
    """새로 확정된 것을 원장에 더한다. **기각할 것만** 돌려준다.

    기각 대상은 위 CORE 참고 -- 주요 인물의 핵심 칸뿐이다. 나머지는 값이 달라져도
    새 값으로 갱신하고 넘어간다. 세계는 자라라고 두는 것이지 붙잡아 두는 것이 아니다."""
    clashes = []

    def _elaborates(old_v: str, new_v: str) -> bool:
        """새 값이 옛 값을 더 자세히 말한 것인가. 판정이 애매하면 **너그러운 쪽**이다."""
        a, b = re.sub(r"\s+", "", old_v), re.sub(r"\s+", "", new_v)
        if a in b or b in a:
            return True
        if difflib.SequenceMatcher(None, a, b).ratio() >= SIMILAR:
            return True
        aw = {w for w in re.split(r"[\s·,]+", old_v) if len(w) >= 2}
        bw = {w for w in re.split(r"[\s·,]+", new_v) if len(w) >= 2}
        return bool(aw & bw)

    def _clean(v):
        return str(v).strip() if isinstance(v, (str, int, float)) and str(v).strip() else None

    # ---- 인물: 카드로 자란다. 주요 인물의 핵심 칸만 기각한다.
    for name, v in (delta.get("people") or {}).items():
        cur = ledger["people"].get(name)
        card = dict(cur) if isinstance(cur, dict) else ({"소개": cur} if cur else {})
        seen = int(card.get("_seen", 0)) + 1
        filled = len([k for k in card if not k.startswith("_")])
        main = seen >= MAIN_AFTER and filled >= MAIN_FIELDS
        fields = v if isinstance(v, dict) else {"소개": v}
        for f, raw in fields.items():
            fv = _clean(raw)
            if fv is None or f == "_seen":
                continue
            old_v = card.get(f)
            if not old_v or old_v == fv:
                card[f] = fv
                continue
            # **죽음은 모순이 아니라 사건이다.** 살아 있던 사람이 죽는 것은 이야기가
            # 나아간 것이고, 죽은 사람이 걸어 들어오는 것만 세계가 무너진 것이다.
            # 시간이 한 방향으로만 가므로 이 칸의 판정도 한 방향이다.
            if "생사" in f or "생존" in f:
                if _DEAD.search(old_v) and not _DEAD.search(fv):
                    clashes.append(f"{name}: 죽었던 사람이 다시 살아 있다 "
                                   f"('{old_v}' → '{fv}')")
                else:
                    card[f] = fv                      # 죽는 것은 그대로 받는다
                continue

            gated = main and any(k in f for k in CORE)
            if not gated:
                card[f] = fv if len(fv) > len(old_v) else old_v   # 자세한 쪽을 남긴다
                continue
            if any(k in f for k in STRICT):
                a, b = re.sub(r"\D", "", old_v), re.sub(r"\D", "", fv)
                if a and a == b:
                    continue
            elif _elaborates(old_v, fv):
                card[f] = fv if len(fv) > len(old_v) else old_v
                continue
            clashes.append(f"{name}의 {f}: 앞에서는 '{old_v}' 였는데 지금 '{fv}' 다")
        card["_seen"] = seen
        ledger["people"][name] = card

    # ---- 나머지: **기록만 한다. 절대 기각하지 않는다.**
    for bucket in ("places", "facts", "objects", "words", "open", "rules",
                   "macguffin"):
        for k, raw in (delta.get(bucket) or {}).items():
            v = _clean(raw)
            if v is None:
                continue
            old_v = ledger[bucket].get(k)
            ledger[bucket][k] = v if not old_v or len(v) > len(str(old_v)) else old_v
    # **언제 놓였는지 적어 둔다.** 회수는 가까운 과거를 향해야 한다 -- 나이를 모르면
    # 첫 장면의 물건이 영원히 "식은 소품" 으로 남아 원고를 처음으로 되돌린다(실측).
    age = ledger.setdefault("_age", {})
    for name in diffusion.props(ledger):
        age.setdefault(name, at)
    # **연 뒤에 닫는다.** 순서가 중요하다 -- 같은 덩어리에서 던졌다가 그 자리에서 답한
    # 것은 미결이 아니라서, 닫힘이 열림보다 나중에 와야 그것이 안 남는다.
    # **압축.** 통칙 하나가 흩어진 사실 몇을 덮으면 그 사실들을 브리핑에서 접는다.
    # 원장에서 지우지는 않는다 -- 정리가 공리를 지우지 않는 것과 같다. 다만 눈앞에서
    # 치워야 프롬프트가 실제로 가벼워진다.
    _folded = ledger.setdefault("_folded", [])
    for k in (delta.get("folded") or []):
        if k and k not in _folded:
            _folded.append(k)

    for k in (delta.get("closed") or []):
        for name in list(ledger.get("open") or {}):
            if k and (k in name or name in k):
                ledger["open"].pop(name, None)
    for t in (delta.get("time") or []):
        if t and t not in ledger["time"]:
            ledger["time"].append(t)
    return clashes


def is_main(card) -> bool:
    """주요 인물인가 -- 자주 나왔고(3회) 카드도 두툼하다(3칸). _merge 와 같은 잣대다."""
    if not isinstance(card, dict):
        return False
    filled = sum(1 for k, v in card.items() if v and not k.startswith("_"))
    return int(card.get("_seen", 0)) >= MAIN_AFTER and filled >= MAIN_FIELDS


# 브리핑에 쓰는 창의 크기와 상한.
#
# **원장은 자라도 브리핑은 자라면 안 된다.** 원고가 길어질수록 인물·장소·사물·사실이
# 쌓이고, 그것이 매 덩어리 프롬프트에 통째로 실리면서 뒤로 갈수록 농도가 올라갔다
# (사용자 평: "뒤로 갈수록 조금 밀도가 높아져서 처음 1/2 지점 정도로 유지해주면 좋겠다").
#
# 그래서 브리핑을 **창(window)** 으로 만든다. 최근 열두 덩어리 안에 놓인 것만 싣고,
# 주요 인물은 나이와 무관하게 늘 싣는다 -- 그 사람들의 카드가 대사를 갈라 놓는 근거라서
# 빠지면 목소리가 무너진다. 그러고도 넘치면 글자 수로 자른다.
#
# 잘려 나간 것이 사라지는 것은 아니다. 원장에는 그대로 남아 모순 검사에 계속 쓰인다 --
# 눈앞에서 치우는 것이지 잊는 것이 아니다.
BRIEF_WINDOW = 12
# 프롬프트에 보여 줄 열린 것의 수. 너무 많으면 숙제 목록이 된다.
OPEN_SHOW = 6
# 이보다 많이 열려 있으면 "좀 닫아라" 고 말한다. 벌리기만 하면 산만해진다.
OPEN_MAX = 9
BRIEF_MAX = 1400


def brief(ledger: dict, limit: int = 40, now: int = 0) -> str:
    """원장을 프롬프트에 실을 형태로.

    **주요 인물만 카드를 통째로 펼친다.** 대사가 인물마다 달라지려면 나이도 말투도
    트라우마도 그 자리에 있어야 하지만, 그건 계속 말하는 사람 이야기다. 5만 자를 쓰면
    스쳐 간 사람이 쉰 명씩 쌓이는데(우체부, 옆자리 손님, 이름만 나온 삼촌) 그들의 카드까지
    매 덩어리에 펼치면 프롬프트가 원장으로 가득 찬다 -- 그러면 정작 읽어야 할 꼬리와 확산
    지시가 뒤로 밀리고, 호출 하나가 무거워져 RPM 도 빨리 마른다.

    그래서 조연은 **한 줄로 접는다.** 접혀 있어도 이름은 남으니 확산의 연료로는 그대로
    쓰인다. 그 사람이 다시 자주 나오기 시작하면 _seen 이 차면서 저절로 펼쳐진다.
    """
    out = []
    age = ledger.get("_age") or {}

    def fresh(k):
        born = age.get(k)
        return born is None or now - born <= BRIEF_WINDOW

    people = list(ledger.get("people", {}).items())
    if people:
        main = [(n, c) for n, c in people if is_main(c)]
        # 조연도 창으로 자른다. **주요 인물만 나이를 안 본다** -- 그 카드가 대사를 갈라
        # 놓는 근거라서 빠지면 목소리가 무너진다. 스쳐 간 사람은 이름만 남아 있으면
        # 되는데, 그 이름이 쉰 개면 그것이 곧 밀도다.
        rest = [(n, c) for n, c in people if not is_main(c) and fresh(n)]
        if main:
            out.append("  [인물]")
            for name, card in main:
                fields = " · ".join(f"{k} {v}" for k, v in card.items()
                                    if v and not k.startswith("_"))
                out.append(f"    {name} — {fields}")
        if rest:
            brief_rest = []
            for name, card in rest[-limit:]:
                if isinstance(card, dict):
                    bit = next((f"{k} {v}" for k, v in card.items()
                                if v and not k.startswith("_")), "")
                else:
                    bit = str(card)
                brief_rest.append(f"{name}({bit})" if bit else name)
            out.append("  [스쳐 간 사람] " + " · ".join(brief_rest))
    # 열린 것은 여기 안 싣는다 -- [열린 것] 블록이 따로 있고, 두 번 실으면 그만큼
    # 프롬프트만 무거워진다.
    if ledger.get("rules"):
        out.append("  [통칙] " + " · ".join(f"{k}: {v}"
                                          for k, v in list(ledger["rules"].items())[-6:]))
    folded = set(ledger.get("_folded") or [])
    for bucket, label in (("places", "장소"), ("objects", "사물"), ("facts", "사실"),
                          ("words", "지어낸 말")):
        items = [(k, v) for k, v in (ledger.get(bucket) or {}).items()
                 if fresh(k) and k not in folded][-limit:]
        if items:
            out.append(f"  {label}: " + " · ".join(f"{k}={v}" for k, v in items))
    if ledger.get("time"):
        out.append("  시간: " + " → ".join(ledger["time"][-6:]))

    text = "\n".join(out) or "  (아직 비어 있다)"
    if len(text) > BRIEF_MAX:
        # 넘치면 뒤에서부터 자른다. 주요 인물 줄이 앞에 있어서 그쪽이 먼저 살아남는다.
        keep, used = [], 0
        for line in out:
            if used + len(line) > BRIEF_MAX:
                keep.append("  (오래된 것은 접었다 -- 원장에는 그대로 있다)")
                break
            keep.append(line)
            used += len(line) + 1
        text = "\n".join(keep)
    return text


# 이어 쓰는 덩어리에만 붙는다. **원고가 첫 장면으로 되돌아간 실측** 때문에 생겼다 --
# 확산이 "다시 만질 것" 으로 첫 문장의 공항과 비행기를 계속 올려 주니 모델이 성실하게
# 거기로 돌아갔다. 나이(diffusion.FUEL_AGE)로 연료를 자르는 것이 근본 대응이고, 이건
# 그 위에 얹는 못이다 -- 재료와 장소를 갈라 말해 준다.
FORWARD = """
  * **이 마지막 문장 다음 순간부터 써라.** 여기가 지금이다.
  * **시간은 앞으로만 간다.** 앞 장면으로 돌아가지 마라. 특히 **첫 장면으로는 절대
    돌아가지 마라** -- 그 공항, 그 비행기, 그 도착은 이미 지나갔다. 회상으로 들르는 것도
    한 덩어리에 한 번을 넘기지 마라.
  * 위 [세계] 에 적힌 것은 **다시 쓸 수 있는 재료**이지 다시 갈 장소가 아니다."""


# ---------------------------------------------------------------- 프롬프트

def _level(book: dict) -> float:
    """이 덩어리의 표류 세기. 원고의 계수를 중심으로 덩어리마다 흔들린다."""
    return matter.level_at(book.get("seed_id") or book["first"],
                           len(book["chunks"]),
                           float(book.get("drift", DRIFT)))


def _must(book: dict) -> str:
    """**맨 끝의 필수 목록.** 모델이 마지막으로 읽는 자리다.

    급발진이 안 나온다는 평(2026-09-05)의 원인은 지시가 없어서가 아니라 **묻혀서**였다.
    프롬프트 한복판에 열 줄짜리 블록으로 있으면 앞뒤의 스무 항목에 섞여 흐려진다.
    그래서 지금 이 덩어리에 반드시 있어야 하는 것만 세 줄로 다시 세운다.
    """
    if book.get("_shock"):
        return ("[이 덩어리에 반드시]\n"
                "  1. 위 사건이 실제로 터진다. 예고하지 말고 터뜨려라\n"
                "  2. 사람마다 다르게 반응한다 -- 화내고, 웃고, 못 본 척하고, 품어 준다. "
                "대사로 받아라\n"
                "  3. 끝나고 공간이 바뀌어 있다")
    has = "급발진 하나" in _impulse(book)
    lines = ["[이 덩어리에 반드시]"]
    if has:
        lines.append("  1. **위 급발진이 실제로 일어난다.** 저지르고 → 사람마다 다르게 "
                     "반응하고(한쪽은 품어 주고) → 저지른 쪽은 태연하다. 빠뜨리면 실패다")
    else:
        lines.append("  1. 급발진은 이번엔 없다. 그래도 인물의 말투와 태도는 그대로다")
    lines.append(f"  2. **대사가 {diffusion.LIMITS['rally']}턴 넘게 이어지는 자리 하나.** "
                 f"그중 하나는 {diffusion.TALK_HUGE}자를 넘는 긴 대사")
    lines.append("  2-1. **점층** -- 앞 문장을 받아 좁히거나·키우거나·뒤집는 문장이 "
                 f"서술문 {rhythm.LIMITS['climb']}개마다 하나")
    lines.append("  3. **욕망 하나가 결판난다.** 채워지면 몸으로 쓰고, 어긋나면 다음 "
                 "욕망이 생긴다")
    lines.append("  4. 잡소리 **둘**. 새것 셋, 앞엣것 하나는 **더 구체적인 이름으로 키워서**")
    if book["ledger"].get("open"):
        lines.append("  5. **열린 것 하나를 건드린다.** 닫든 벌리든 바꾸든")
    return "\n".join(lines)


def _bond(book: dict) -> str:
    seed = book.get("seed_id") or book["first"]
    n = len(book["chunks"])
    if not bond.gate(seed, n, float(book.get("bond", BOND))):
        return ""
    return bond.brief(bond.draw(seed, n))


def _trait(book: dict) -> str:
    seed = book.get("seed_id") or book["first"]
    n = len(book["chunks"])
    # 옛 원고는 'body' 로 저장돼 있다 -- 이름이 바뀌었다고 설정을 잃게 하지 않는다.
    rate = float(book.get("trait", book.get("body", TRAIT)))
    if not trait.gate(seed, n, rate):
        return ""
    return trait.brief(trait.draw(seed, n))


def _doubt(book: dict) -> str:
    from novel import diffusion as _D
    if len(_D.props(book["ledger"])) < 4:
        return ""
    seed = book.get("seed_id") or book["first"]
    n = len(book["chunks"])
    if not doubt.gate(seed, n, float(book.get("doubt", DOUBT))):
        return ""
    return doubt.brief(doubt.draw(book["ledger"], seed, n))


def _pov(book: dict) -> str:
    seed = book.get("seed_id") or book["first"]
    n = len(book["chunks"])
    if n < 3 or not doubt.gate(seed, n, float(book.get("pov", POV)), "pov"):
        return ""
    return doubt.pov_brief(doubt._pick(doubt.POV, seed, n, "pov"))


def _macguffin(book: dict) -> str:
    """**맥거핀** -- 모두가 쫓는데 정체는 끝내 안 밝혀지는 것.

    미결(open)과 헷갈리기 쉬운데 반대다. 미결은 언젠가 손대라고 올려 주는 것이고,
    맥거핀은 **손대지 말라고** 올려 주는 것이다. 그것이 무엇인지가 밝혀지는 순간
    이야기의 동력이 꺼진다 -- 사람들이 그것을 쫓는 동안에만 살아 있다.
    """
    m = book["ledger"].get("macguffin") or {}
    if not m:
        return ""
    name, why = list(m.items())[-1]
    return f"""[맥거핀] **{name}** -- {why}

  * **정체를 밝히지 마라.** 이번에도, 다음에도. 그것이 무엇인지 아무도 모르는 채로
    사람들이 그것 때문에 움직인다.
  * 사람마다 **다르게 알고 있다.** 누구는 물건이라 하고 누구는 사람이라 하고 누구는
    그런 건 없다고 한다. 그 어긋남이 이야기를 민다.
  * 가까이 갈수록 **다른 것이 나온다.** 답 대신 새 질문이 나오게 해라.
  * 이것만은 [열린 것]에서 닫지 마라. 닫는 순간 동력이 꺼진다."""


def _exception(book: dict) -> str:
    """**반례** -- 세워 둔 통칙을 한 번 깨서 세계를 정교하게 만든다.

    수학은 반례로 명제를 좁힌다. 소설에서도 규칙에 예외가 나오는 순간 그 규칙이 진짜가
    된다 -- 아무도 안 깨는 규칙은 규칙이 아니라 배경이다.

    **사실의 모순과 다른 물건이다.** 마흔둘이던 사람이 서른이 되는 것은 기각이지만,
    '겨울엔 배를 안 띄운다' 는 통칙을 누가 한 번 깨는 것은 환영이다. 앞의 것은 세계가
    무너지는 일이고 뒤의 것은 세계가 두꺼워지는 일이다.
    """
    rules = list((book["ledger"].get("rules") or {}).items())
    if not rules:
        return ""
    seed = book.get("seed_id") or book["first"]
    n = len(book["chunks"])
    if not bridge.gate(seed + "|exc", n, float(book.get("exception", EXCEPTION))):
        return ""
    name, text = rules[bridge._raw(rules, seed, n, "rule")]
    return f"""[예외] **세워 둔 통칙 하나를 이번에 깨라.**

  · 통칙 -- **{name}: {text}**

  * 누가 그것을 어긴다. **규칙은 지워지지 않는다** -- 예외가 규칙을 정교하게 만든다.
    "그런데 그 사람은" 이 붙는 순간 세계가 두꺼워진다.
  * **왜 어겼는지 설명하지 마라.** 어기는 데는 이유가 있고, 그 이유는 본인 사정이다.
  * 남들이 그것을 어떻게 보는지가 더 중요하다 -- 말리는 쪽, 모른 척하는 쪽, 따라 하는 쪽.
  * **이건 모순이 아니다.** 통칙과 예외는 같이 참이다. 사실을 뒤집는 것과 헷갈리지 마라 --
    한 사람의 나이나 생사가 바뀌는 것은 여전히 기각이다."""


def _bridge(book: dict) -> str:
    from novel import diffusion as _D
    if len(_D.props(book["ledger"])) < BRIDGE_AFTER:
        return ""
    seed = book.get("seed_id") or book["first"]
    n = len(book["chunks"])
    if not bridge.gate(seed, n, float(book.get("bridge", BRIDGE))):
        return ""
    return bridge.brief(bridge.draw(book["ledger"], seed, n))


# 곁들이 축. **한 덩어리에 하나만 실린다.**
#
# 전부 각자 비율로 켜지게 두었더니 절반 넘는 덩어리에 둘 이상이 겹쳤고(실측 100덩어리:
# 2개 34회 · 3개 17회 · 5개 3회), 프롬프트가 18,000자를 넘었다. 그러면 급발진이 아홉
# 목소리 중 하나가 된다 -- 계수는 1.0 이라 매번 켜져 있는데도 원고에는 안 나온다.
# 사용자 평(2026-09-05): "주인공의 급발진이 적어."
#
# **덜 시키면 더 나온다.** 급발진과 확산은 매번 가고, 나머지는 이 중 하나만 곁들인다.
SIDES = ("bond", "trait", "doubt", "bridge", "exception", "pov", "matter")


def _side(book: dict) -> str:
    """이번 덩어리의 곁들이 하나. 켜진 것들 중에서 하나만 고른다."""
    makers = {"bond": _bond, "trait": _trait, "doubt": _doubt, "bridge": _bridge,
              "exception": _exception, "pov": _pov, "matter": _matter}
    ready = [(k, t) for k in SIDES for t in [makers[k](book)] if t]
    if not ready:
        return ""
    seed = book.get("seed_id") or book["first"]
    n = len(book["chunks"])
    return ready[doubt._raw(ready, seed, n, "side")][1]


def _open(book: dict) -> str:
    """**열린 것** -- 이 이야기가 아직 갚지 않은 것들.

    닫으라고 시키지 않는다. 시키는 순간 그것이 각본이 되고, 각본은 이 모드가 버린 것이다.
    **하나를 건드리게만 한다** -- 닫아도 되고, 더 벌려도 되고, 다른 것으로 바꿔도 된다.
    """
    items = list((book["ledger"].get("open") or {}).items())
    if not items:
        return ""
    show = " · ".join(f"**{k}**({v})" for k, v in items[-OPEN_SHOW:])
    crowd = ("\n  * 열린 것이 {n}개다. 벌리기만 하면 산만해진다 -- 이번엔 **하나쯤 닫아라.** "
             "답이 시원할 필요는 없다. 김빠지는 답도 답이다.").format(n=len(items)) \
        if len(items) > OPEN_MAX else ""
    return f"""[열린 것] **이 이야기가 아직 갚지 않은 것들.**

  {show}

  * 이 중 **하나를 건드려라.** 닫아도 되고, 더 벌려도 되고, 엉뚱한 답이 나와서 다른
    것으로 바뀌어도 된다. **닫으라는 것이 아니다** -- 손을 대라는 것이다.
  * 건드리는 방식은 자유다. 누가 그 얘기를 꺼내도 되고, 물건 하나가 답이 되어도 되고,
    아무도 모르는 채로 독자만 알게 되어도 된다.
  * **새로 여는 것도 좋다.** 다만 닫는 것 없이 열기만 하면 그건 나열이다.{crowd}"""


def _matter(book: dict) -> str:
    """**소재** -- 이번 덩어리에 섞을 재료. 확산·리듬이 '어떻게' 라면 이건 '무엇' 이다.

    이 축이 없을 때 모델은 늘 비슷한 것을 냈다 -- 술집, 부두, 낡은 차, 담배. 세계가
    넓어져도 재료가 안 넓어졌다.
    """
    seed = book.get("seed_id") or book["first"]
    n = len(book["chunks"])
    rate = float(book.get("matter", MATTER))
    if not matter.gate(seed, n, "matter", rate):
        return ""
    return matter.brief(matter.draw(seed, n, _level(book)))


def _impulse(book: dict) -> str:
    """**급발진** -- 인물이 스스로 저지르는 것. 사건(shock)과 다른 물건이다.

    사건은 밖에서 들이닥쳐 점층을 끊는다. 급발진은 흐름 **안에서** 한 번 튄다 -- 세계가
    바뀌지 않고 분위기만 바뀌므로, 확산을 대신하지 않고 확산 안에 들어간다. 그래서 매
    덩어리에 하나씩 걸어도 된다. 뽑기는 덩어리 번호에 묶여 이어 쓰기에도 재현된다.
    """
    seed = book.get("seed_id") or book["first"]
    n = len(book["chunks"])
    # 계수만큼만 켠다. 꺼진 덩어리에서도 성격은 그대로다 -- 저지르지 않을 뿐이다.
    if not matter.gate(seed, n, "impulse", _level(book)):
        return ("  * 이번 덩어리에는 급발진을 넣지 마라. 그렇다고 사람이 바뀌는 것은"
                " 아니다 -- 저지르지 않을 뿐, 말투도 태도도 그대로다.")
    return SH.impulse_brief(SH.impulse(seed, n))


def _push(book: dict) -> str:
    """이 덩어리가 할 일 -- **평소엔 확산, 사건 차례엔 사건.**

    사건은 확산을 **한 덩어리만** 대신한다. 터지고 나면 다음 덩어리부터 다시 점층이다 --
    다만 그때의 세계는 사건이 바꿔 놓은 세계라, 같은 자리에서 다시 쌓지 않는다.
    """
    if book.get("_shock"):
        return SH.brief(book["_shock"]) + """

  * 다음 덩어리부터는 **다시 점층이다.** 사건은 여기서 한 번 끊는 것이지 방향을 바꾸는
    것이 아니다. 이 사건이 남긴 것에서 다시 쌓기 시작한다."""
    return _diffuse(book)


def _wording(book: dict) -> str:
    """말맛 장부 -- 쓴 말끝은 세어 두고 안 쓴 쪽으로 민다. 비유와 글의 꼴은 뽑아서 흔든다."""
    return wording.brief(book["chunks"],
                         book.get("seed_id") or book.get("first", ""),
                         len(book["chunks"]),
                         out_span=GENRE.tune(book.get("genre", ""), "밖", None))


def _genre(book: dict) -> str:
    """갈래 몫. 갈래가 없으면 빈 줄 -- 지금까지의 틀 그대로 돈다."""
    return GENRE.brief(book.get("genre", ""),
                       book.get("seed_id") or book.get("first", ""),
                       len(book["chunks"]))


def _talklong(book: dict) -> float:
    """이 덩어리에서 긴 대사가 차지할 몫. 자와 프롬프트가 **같은 숫자**를 봐야 한다 --
    따로 뽑으면 시키는 것과 재는 것이 어긋난다."""
    return rhythm.aim(f"{book.get('seed_id') or book.get('first', '')}|talklong",
                      len(book["chunks"]), book.get("seen_talk", []),
                      diffusion.LONG_LO, diffusion.LONG_HI)


def _climb(book: dict) -> str:
    """점층의 이음말을 **뽑아서** 준다. 프롬프트에 서넛을 박아 두었더니 원고가 그 서넛으로
    도배됐다(사용자 평: "'정확히 말하자면' 이 너무 많이 나와"). 자는 스물 몇 개를 세는데
    프롬프트는 넷만 보여 줬으니, 모델이 아는 것이 넷뿐이었던 것이다."""
    picked = SH._batch(rhythm._CLIMB, f"{book.get('seed_id') or book.get('first', '')}|climb",
                       len(book["chunks"]), "climb", 6)
    return " · ".join(f"'{x}'" for x in picked)


def _dialogue(book: dict) -> float:
    """이 덩어리에서 **대사가 차지할 몫.** 절반 언저리를 조준한다 -- 대사가 이야기를
    밀고, 정보는 대사에 녹는다. 고정 하한을 두면 그 하한이 다시 주기가 된다."""
    lo, hi = GENRE.tune(book.get("genre", ""), "대사",
                        (rhythm.TALK_LO, rhythm.TALK_HI))
    return rhythm.aim(f"{book.get('seed_id') or book.get('first', '')}|talkshare",
                      len(book["chunks"]), book.get("seen_dlg", []), lo, hi)


def _telllong(book: dict) -> float:
    """이 덩어리에서 긴 **서술문**이 차지할 몫. 지난 덩어리에서 실제로 나온 값을 보고
    모자란 쪽으로 민다 -- 눈감고 흔들기만 하면 시킨 것과 나온 것이 어긋나도 모른다."""
    return rhythm.aim(f"{book.get('seed_id') or book.get('first', '')}|telllong",
                      len(book["chunks"]), book.get("seen_tell", []),
                      rhythm.LONG_LO, rhythm.LONG_HI)


def _diffuse(book: dict) -> str:
    """**확산 지시** -- 뒤로 갈수록 옅어지는 것을 여기서 막는다.

    다음 덩어리에게 넘어가는 것은 꼬리 900자뿐이라, 세 덩어리 앞의 소품은 창 밖으로
    빠진다. 그래서 **식은 소품을 이름으로 짚어 다시 올려준다.** 원장을 제약이 아니라
    재료로 쓰는 자리가 여기다.
    """
    fuel = diffusion.cold(book["ledger"], "".join(book["chunks"])[-TAIL:],
                          now=len(book["chunks"]))
    pick = ("  * 이번에 다시 만질 것 -- " + " · ".join(fuel[:8]) + "\n"
            "    이 중 **둘 이상**을 다시 꺼내되, 똑같이 쓰지 마라. 한 단계 키운다:\n"
            "      그냥 놓여 있던 것이 → 쓰이거나 · 망가지거나 · 없어지거나 ·\n"
            "      다른 사람 손에 있거나 · 그것 때문에 일이 생긴다\n") if fuel else ""
    return f"""[확산] **이야기는 뒤로 갈수록 짙어져야 한다 -- 옅어지면 실패다.**

한 덩어리는 세계를 **넓히고(새것)** 동시에 **깊게 한다(앞엣것을 키운다).** 둘 중 하나만
하면 산만해지거나 제자리를 돈다. 이건 재서 판정한다:

  * 새로 놓는 것 **{diffusion.LIMITS['new']}개 이상** -- 새 사람, 새 장소, 새 물건, 새 사실.
    이름을 붙이되 **연식·산지·상표를 접두사로 달지 마라**('1982년형 볼보', '1978년산
    판화집' 처럼). 연도 표기는 이 덩어리에 {diffusion.LABEL_MAX}개까지다. 구체성은 명사를
    꾸미는 데서 오지 않고 **그것이 무엇을 하는가**에서 온다. 상황 설명으로 분량을 채우지 마라.
  * 앞에서 나온 것 **{diffusion.LIMITS['back']}개 이상**을 다시 만진다. 다만 **한 이름을
    {diffusion.ECHO_MAX}번까지만 부른다** -- 회수는 다시 부르는 것이 아니라 다시 쓰는 것이다.
    두 번째부터는 '그것', '그 차', '그 종이' 로 받아라.
{pick}
[대사가 이야기다] **설명으로 넘기지 말고 말로 진행시켜라.**
  * 긴 대사 **{diffusion.LIMITS['long']}개 이상**({diffusion.TALK_LONG}자 넘게) -- 누가 한 번은
    길게 떠든다. 변명이든, 수다든, 아무도 안 물어본 집안 내력이든, 틀린 지식이든.
    **소품의 유래는 서술이 아니라 이 자리에서 나온다.**
  * **이 대목은 대사 줄의 {_talklong(book):.0%}가 {diffusion.TALK_LONG}자를 넘는다 -- 이건 재서 판정한다.**
    이 숫자는 **덩어리마다 다르다.** 어떤 대목은 여덟 할이 길고 어떤 대목은 둘만 길다 --
    한 숫자로 매번 맞추면 그것도 한 가지 가락이다.
    **기본은 길게 말하는 것**이다. 할 말이 있으면 다 하고, 딴 얘기로 새고, 묻지 않은
    것까지 말한다. {diffusion.TALK_SHORT}자 이하로 짧게 끊는 것은 **앞사람 말에 기대는 한 마디**일
    때뿐이고, 내리 {diffusion.LIMITS['srun']}번을 넘으면 주고받기가 아니라 딸꾹질이다.
  * **종결어미를 매번 다르게, 그리고 이상하게 끝내라.** '-다/-요/-까' 로만 끝내지 마라 --
    말을 하다 말고, 되묻고, 혼잣말로 흘리고, 남의 말투를 흉내 내다 만다. 말끝은 그
    사람이 지금 어떤 상태인지를 드러내는 자리다.
  * **뻘소리를 해라. 정신 나간 소리를 해라.** 아무도 안 궁금해하는 것을 길게 설명하고,
    자기만 아는 규칙을 진지하게 대고, 방금 한 말을 스스로 반박한다. 대사가 문장처럼
    반듯해지면 그건 사람 말이 아니라 자막이다.
  * **정보를 잔뜩 섞어라 -- 묻지도 않은 것까지.** 긴 대사 하나에 서로 상관없는 것이
    서넛은 들어간다: 연도, 값, 사람 이름, 지명, 규격, 남의 집 사정, 잘못 아는 상식.
    말하는 사람은 그것들이 다 이어져 있다고 믿는다. 듣는 사람만 모른다.
  * **느낌표를 써라.** 감정이 세서가 아니라 말이 빨라져서 붙는 느낌표다 -- 별것
    아닌 데서 터지고, 정작 큰일에는 안 붙는다. 물음표와 붙여 써도 되고, 말끝에
    두 개가 와도 된다. 다만 온 문장이 느낌표면 그건 비명이지 대사가 아니다.
  * **긴 대사 하나는 아주 길게.** 한 사람이 자기 얘기에 빠져서 백스무 자를 넘겨라 --
    그 안에서 스스로 말을 고치고, 딴 데로 샜다가, 돌아온다. 두 마디짜리와 열 줄짜리가
    같은 장면 안에 있어야 주고받기가 된다.
  * **묘사 한가운데로 대사가 뛰어들어도 된다.** 따옴표 없이, 쉼표 사이로.
  * **이상한 대화를 해라.** 지금 상황과 상관없는 것을 궁금해하고, 엉뚱한 데서 정색하고,
    농담을 무표정하게 던진다. 용건만 오가는 대사가 제일 재미없다.
  * **감탄사를 새로 지어내고 문법을 놓아라.** 앞 덩어리에 쓴 감탄사를 또 쓰지 마라 --
    매번 새 소리다. 문장을 끝까지 맺지 않아도, 어순이 뒤집혀도, 조사가 빠져도 된다.
    **말끝을 다듬으면 그게 딱딱함이다.**

{_impulse(book)}
{_open(book)}
{_macguffin(book)}
{_side(book)}
[잡소리] **쓸데없는 말이 이 소설의 재미다. 이 덩어리에 적어도 하나는 넣어라.**
다만 **전부 하려 들지 마라.** 여섯을 다 채우면 그게 버릇이 되고, 버릇이 되는 순간
안 웃긴다. **둘은 반드시, 셋까지.** 그리고 늘 같은 수를 쓰지 마라.
  · **TMI** -- 아무도 안 물어본 자기 얘기를 주저리주저리 늘어놓는다. 중요한 건 **듣는
    쪽의 반응**이다. 감탄해 주지 않는다 -- 끊거나, 딴 데를 보거나, 쿠사리를 주거나,
    자기 얘기로 덮어 버린다. 그 핀잔을 **그 사람이 쓸 법한 말로** 써라. 그래도 말하던
    쪽은 하던 얘기를 마저 한다.
  · **회상** -- 지금 상황과 상관없는 옛일이 불쑥 떠오른다. 교훈으로 쓰지 마라. 그냥
    떠오르고, 아무 결론 없이 끝난다.
  · **지극히 개인적인 일** -- 남이 들으면 아무것도 아닌데 본인에게는 중대한 것.
    발톱이 부러진 것, 십 년째 못 버리는 컵, 누구한테도 말 안 한 버릇.
  · 멍청한 소리를 아주 진지하게 한다. 아무도 안 웃는다
  · 지금 상황과 아무 상관없는 것을 두고 둘이 다툰다
  · 틀린 지식을 자신 있게 말하고, 아무도 고쳐 주지 않는다
  · 별명을 붙인다. 본인만 모른다

[전개] **한 덩어리 안에서 인물이 여러 가지를 실제로 한다.**
한 자리에 앉아 생각만 하다 끝나면 그게 정체다. 큰일 하나와 사소한 일 두셋이 **줄줄이
이어지며** 굴러가야 한다 -- 하던 일을 하다가, 몸을 챙기다가, 딴 데로 새다가, 다시 돌아온다.
  * **행위에서 행위로 넘어가라.** 장면을 설명으로 잇지 말고 다음 동작으로 이어라.
  * 그 일들이 서로 어울릴 필요는 없다. **위험한 일과 시시한 일이 붙어 있을수록 좋다.**
  * 무엇을 하는지는 **네가 정해라.** 인물의 직업·형편·버릇에서 나오는 것이면 된다 --
    일이든 돈벌이든 뒷거래든 병원이든 끼니든 습관이든.
  * 하나하나를 다 설명하지 마라. 지나가듯 두고 다음으로 가라.

[전환] **외현에서 내현으로.** 이 덩어리 어딘가에서 한 번은 넘어가라 -- 사물·풍경·행동을
보다가 생각·기억·잃어버린 것으로. 그 자리에서만 넘어간다. 넘어가는 지점은 매번 달라야
한다."""


# 자리를 짚어 고칠 수 있는 갈래. 나머지(대사 비율·점층·박자·확산)는 새 재료가 있어야
# 하므로 문장 교체로는 안 되고, 예전처럼 다시 쓴다.
PATCHABLE = {
    "da":   "이 문장들이 **짧은 '-다'** 로 끝난다. 끝을 바꿔라 -- 명사로 끝내거나,"
            " 말줄임으로 두거나, '-까/-지/-군/-는 것' 으로 바꾸거나, 뒤에 생각을 붙여라.",
    "run":  "짧은 '-다' 가 내리 이어진 자리다. 끝을 바꾸거나 앞 문장에 이어 붙여라.",
    "long": "이 문장들이 너무 짧다. **쉼표로 이어 붙여** 마흔다섯 자를 넘겨라 --"
            " 딴 생각이든, 눈에 들어온 것이든, 방금 한 말의 토를 달든.",
}


def echo_lines(text: str, prior: str) -> list:
    """앞 원고에 이미 있는 문장만 골라낸다."""
    if not prior:
        return []
    tell, _ = rhythm._lines(text)
    return [s for s in tell if len(s) >= 12 and s in prior]


def clash_lines(text: str, clashes: list) -> list:
    """모순에 걸린 이름이 나오는 문장만 골라낸다. 원고를 통째로 버리지 않으려고."""
    names = set()
    for c in clashes:
        m = re.match(r"\s*([^:의]+)", c)
        if m and m.group(1).strip():
            names.add(m.group(1).strip())
    tell, _ = rhythm._lines(text)
    return [s for s in tell if any(n in s for n in names)][:8]


def clash_prompt(clashes: list, lines: list) -> str:
    """**어긋난 문장만 고쳐 달라고 한다.** 예전에는 여섯 번 다 못 넘기면 3,200자를
    통째로 버리고 처음부터 다시 썼다 -- 밤새 돌 때 시간을 제일 많이 먹던 자리다.
    모순은 원고 전체가 아니라 한두 문장에 있다."""
    why = "\n".join(f"  · {c}" for c in clashes)
    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(lines))
    return f"""아래 문장들이 이 소설에서 앞서 확정된 것과 어긋난다.

[어긋난 것]
{why}

[문장]
{numbered}

규칙:
- **앞에서 확정된 쪽이 맞다.** 그것에 맞게 이 문장들을 고쳐라.
- 사건은 그대로 둔다. 같은 일이 같은 순서로 일어나야 한다.
- 짧아지지 마라.
- 번호를 그대로 붙여 **고친 문장만** 돌려줘라.

{{"1": "고친 문장"}} 꼴의 JSON 하나로만 답한다.
"""


def mend_prompt(items: list) -> str:
    """**걸린 데를 한 번에 전부 고쳐 달라고 한다.**

    예전에는 갈래를 하나씩, 시도를 나눠 가며 보냈다 -- 결함이 넷이면 호출이 넷이다.
    문장마다 무엇이 문제인지 적어 한 장에 담으면 호출 하나로 끝난다. 원고를 다시
    받지도 않는다: 보내는 것은 걸린 문장뿐이고 받는 것은 고친 문장뿐이다."""
    numbered = "\n".join(f"{i + 1}. [{why}] {s}" for i, (s, why) in enumerate(items))
    return f"""아래는 어떤 소설에서 뽑아낸 문장들이다. 각 문장 앞 대괄호가 그 문장의
문제다. **전부 고쳐라 -- 하나도 빼지 마라.**

{numbered}

규칙:
- **뜻과 사건은 그대로 둔다.** 같은 일이 같은 순서로 일어나야 한다.
- 사람·장소·물건의 이름을 바꾸지 마라. 새 사건을 만들지 마라.
- 짧아지지 마라. 고친 문장이 원래보다 짧으면 안 고친 것만 못하다.
- 번호를 그대로 붙여 **고친 문장만** 돌려줘라. 다른 말은 쓰지 마라.

{{"1": "고친 문장", "2": "고친 문장"}} 꼴의 JSON 하나로만 답한다.
"""


def mend_items(text: str, clashes: list, prior: str = "") -> list:
    """이 덩어리에서 고칠 것을 **전부** 모은다 -- (문장, 무엇이 문제인가) 목록으로.

    한 문장이 두 갈래에 걸리면 앞엣것만 남긴다. 같은 문장을 두 번 보내면 모델이
    어느 쪽을 따를지 알 수 없고, 번호가 겹쳐 되받은 것을 못 끼운다."""
    items, seen = [], set()
    # **메아리는 모순과 같은 급이다** -- 취향이 아니라 결함이다. 앞에 쓴 문장을 그대로
    # 다시 뱉은 것은 새 글이 아니다(실측: 한 덩어리 2,024자 중 610자가 글자 하나 안
    # 틀리고 반복이었다). 앞머리를 옮겨 적은 것은 echo.trim 이 도려내고, 그러고도
    # 남은 반복은 여기서 그 문장만 새로 쓰게 한다.
    for line in echo_lines(text, prior):
        if line not in seen:
            seen.add(line)
            items.append((line, "앞에 이미 쓴 말이다 -- 같은 말 말고"
                                " **그 다음에 일어나는 일**을 써라"))
    for line in clash_lines(text, clashes):
        if line not in seen:
            seen.add(line)
            items.append((line, "앞에서 확정된 것과 어긋난다 -- 앞엣것이 맞다"))
    spot = rhythm.spots(text)
    for kind, why in PATCHABLE.items():
        for line in spot.get(kind, []):
            if line not in seen:
                seen.add(line)
                items.append((line, why))
    return items[:MEND_MAX]


def apply_patch(text: str, lines: list, fixed: dict) -> tuple:
    """받아 온 문장을 원문에 끼워 넣는다. 못 찾거나 짧아졌으면 그 자리는 그냥 둔다 --
    되받은 것을 검사 없이 넣으면 원고가 조용히 상한다."""
    done = 0
    for key, new in fixed.items():
        try:
            old = lines[int(str(key).strip()) - 1]
        except (ValueError, IndexError, TypeError):
            continue
        new = str(new).strip()
        if not new or new == old or len(new) < len(old) * 0.8:
            continue
        if text.count(old) != 1:          # 여러 군데면 어느 것인지 알 수 없다
            continue
        text = text.replace(old, new, 1)
        done += 1
    return text, done


def write_prompt(book: dict, feedback: str = "") -> str:
    tail = "".join(book["chunks"])[-TAIL:]
    opening = not book["chunks"]
    return f"""{'이 문장으로 소설을 연다' if opening else '아래 글을 이어서 쓴다'}.

{style.narrator()}

[이 소설의 온도] **가볍고 재미있게.** 무겁게 가지 마라. 큰일 앞에서도 사소한 것을 신경
쓰고, 농담은 무표정하게 던지고, 과장된 반응은 옆 사람이 한다. 비장해지려는 문장이 나오면
그 다음 줄에서 김을 빼라.

[대사] **인물에 맞게.** 소설 전체에 한 가지 말투를 씌우지 마라 -- 거친 것은 어떤 인물의
특징이지 이 소설의 규칙이 아니다.
- 아래 [세계]의 인물 카드에 **말투**가 적혀 있으면 그대로 쓴다. 마흔둘 정비공과 스물셋
  대학원생과 예순의 어머니는 같은 문장을 쓰지 않는다.
- 카드에 없는 인물이면 **지금 정하고, 그 다음부터 그대로 간다.** 나이·성격·직업·과거가
  말투를 정한다. 정한 것은 추출기가 카드에 적어둔다.
- **호칭과 말높임은 관계가 정한다.** 처음 만난 사람에게 "너" 라고 하지 않는다 -- 그건
  주인공이 무례해서가 아니라 한국어가 그렇게 안 굴러가서다. 모르는 사람은 "저기요",
  직함이 있으면 직함, 이름을 알면 이름에 "씨" 나 호칭을 붙인다. 반말은 **사이가
  가까워졌거나, 일부러 낮추는 것**이고, 후자면 그 자체가 사건이다.
- **부를 말이 없으면 그것도 쓴다** -- 이름을 모르는 채로 대화가 굴러가는 것, 뭐라고
  불러야 할지 몰라 문장을 비켜 가는 것. 그 어색함이 관계를 보여 준다.
- 말을 끊고, 겹치고, 대답 대신 딴소리를 하는 것은 누구나 한다. 어휘는 자유다 -- 상표든
  욕이든 외국어든 사투리든 **그 사람이 쓸 법한 말**을 그대로 쓴다.

[어디로 가든] **미리 정하지 마라.** 살인이든 불륜이든 사랑이든 실종이든, 지금 쓰는
문장이 다음을 부르는 대로 간다. 앞 덩어리와 크게 상관없는 곳으로 새도 좋다 -- 사람은
원래 상관없는 일들 사이에 산다.
- 새 인물이나 장소가 나오면 **그 사람의 사정을 하나 더 만들어라.** 그 사정이 또 다음
  사람을 부른다. 세계는 그렇게 연쇄로 넓어진다.
- 넓히기만 하고 회수하지 않아도 된다. 끝맺지 않은 것이 남아 있는 편이 진짜 같다.

[리얼리즘] **편의주의 금지 -- 하루에 두 번 울리는 종을 쓰지 마라.**
- 우연이 문제를 풀지 않는다. 필요한 순간에 딱 맞춰 나타나는 사람·전화·열쇠·기억을 쓰지
  마라. 우연은 문제를 **만들 때만** 써라.
- 인물은 화자를 돕기 위해 움직이지 않는다. 자기 사정 때문에 움직이고, 그러다 화자에게
  도움이 되거나 방해가 된다.
- 정보는 대가를 치르고 얻는다. 누가 그냥 설명해주지 않는다. 물어도 대답을 안 하거나,
  절반만 하거나, 틀리게 한다.
- 실패한 것은 실패한 채로 둬라. 잃은 것을 뒤에서 돌려주지 마라.
- 몸은 회복이 느리고, 돈은 모자라고, 날씨는 사정을 봐주지 않는다.

규칙:
- 약 {CHUNK}자를 쓴다. 끊지 말고 이어라. 회차도 씬도 없다.
- **줄거리를 미리 정하지 마라.** 지금 문장에서 다음 문장이 나오게 하라.
- **길이를 섞어라 -- 이건 재서 판정한다.** 다 쓴 뒤 코드가 세어 보고, 넘으면 숫자를
  돌려주며 다시 시킨다:
    · **이 대목은 마흔다섯 자 넘는 긴 문장이 서술문의 {_telllong(book):.0%}다.** 이 숫자는
      덩어리마다 다르다 -- 어떤 대목은 길게 흘러가고 어떤 대목은 짧게 끊어 간다
    · **몰지도, 고르게 맞추지도 마라.** 짧은 문장이 내리 {rhythm.SHORT_RUN}개를 넘으면 그 자리를
      긴 문장으로 끊고, 긴 문장이 내리 {rhythm.LONG_RUN}개를 넘으면 짧은 문장으로 끊어라.
      그렇다고 짧은 것 셋에 긴 것 하나를 규칙적으로 놓으면 그건 리듬이 아니라 박자표다 --
      어떤 데서는 다섯이 이어지고, 어떤 데서는 긴 것이 둘 연달아 온다.
      **리듬은 몫이 아니라 배치다**
    · **짧은 '-다'** 로 끝나는 서술문이 62% 아래. 긴 '-다' 는 세지 않는다 --
      단조로움의 정체는 종결어미가 아니라 길이다
    · 짧은 '-다' 가 내리 **네 번**을 넘지 않는다. 셋째나 넷째에서 생각을 붙이거나,
      대사를 넣거나, 문장을 끝내지 마라
    · **이 대목은 대사가 전체 줄의 {_dialogue(book):.0%}다.** 대사가 이야기를 민다 --
      설명하지 말고 **말하게 해라.** 내력도 사정도 숫자도 대사 안에 녹는다.
      이 숫자도 덩어리마다 다르다
    · **서술문 {rhythm.LIMITS["climb"]}개마다 하나는 앞 문장을 받아 올린다.** 문장은
      낱개로 서 있으면 안 된다 -- 놓았으면 다음 문장이 더 좁히거나, 더 키우거나,
      뒤집어야 한다. 이번 대목에서 써 볼 이음말: {_climb(book)}
      **이것만 쓰라는 것이 아니다.** 매번 같은 말로 받으면 그 말이 버릇이 된다 --
      목록에 없는 것으로 받아도 되고, 이음말 없이 받아도 된다
- **앞에 쓴 문장을 다시 적지 마라.** [지금까지의 끝부분]은 읽으라고 준 것이지 옮겨
  적으라고 준 것이 아니다. 그 다음 문장부터 시작해라. 분량이 모자라면 앞 문단을
  복사하지 말고 **새 일이 일어나게** 해라.
- 사람과 장소의 이름을 구체적으로 대라. 없는 것도 있는 것처럼 자세히 -- 다만 그 자세함이
  수식어가 아니라 **행동과 사정**으로 오게 해라.
{D.SPLIT}
[표류가 먼저다] **아래 뽑기는 전부 출발점이지 각본이 아니다.**
어울리지 않으면 비틀고, 더 나은 것이 떠오르면 버려라. 목록을 채우려고 쓰지 마라 --
글이 가려는 데가 있으면 그리로 가라. **자유도가 이 소설의 첫 번째 규칙이다.**
꺾이지 않는 것은 둘뿐이다: 앞에서 쓴 것과 어긋나지 않기, 우연이 문제를 풀지 않기.

[세계 — 지금까지 놓인 것들]
{brief(book['ledger'], now=len(book['chunks']))}
  * **가끔은 층을 올려라.** 앞에서 구체적으로 놓인 것이 나중에 더 넓은 것의 한 사례로
    다시 나온다 -- 물건 하나가 몇 번 손을 옮기고 나면 그것은 물건이 아니라 빚이거나
    약속이거나 사람 사이의 어떤 규칙이 된다. **그 낱말을 대지는 마라.** 물건은 그대로
    두고 쓰임만 바꿔라.
  * **넓히되 부정하지 마라.** 새로 놓는 것은 여기 있는 것을 품은 채 그 바깥이어야 한다 --
    앞에 쓴 것을 뒤집는 것은 확장이 아니라 다른 이야기다.
  * 이건 금지 목록이 아니라 **연료다.** 여기 있는 것을 다시 꺼내 쓰는 것이 이 소설의
    본체다. 어긋나게만 쓰지 마라 -- 나머지는 전부 자유다.
  * 여기 없는 것은 **새로 지어내도 된다.** 지어냈으면 자세히 지어내라 -- 이름, 연도,
    누가 지었는지, 왜 그렇게 불리는지.
  * 인물이 새로 나오면 **그 자리에서 사람을 만들어라.** 나이와 키, 성격, 가족, 과거,
    트라우마, 좋아하는 것, 취미, 전공, 직업, 말투, 버릇까지. 전부 한 번에 늘어놓지는 마라 --
    지금 필요한 두세 개만 문장에 녹이고, 나머지는 뒤에서 하나씩 드러낸다.

{'[첫 문장 — 이것으로 시작하라]' if opening else '[지금까지의 끝부분 — 여기서 이어 쓴다]'}
{book['first'] if opening else '...' + tail}
{'' if opening else FORWARD}

{_wording(book)}

{OPENING if opening else _push(book)}

{_genre(book)}

{turned(book)}

{owed_brief(book)}

{_must(book)}
{feedback}
산문만 출력한다. 제목도 머리말도 표식도 쓰지 마라."""


def extract_prompt(chunk: str) -> str:
    return f"""아래 글에서 **새로 확정된 사실만** 뽑아 JSON 으로 옮긴다.

{chunk}

규칙:
- 확정된 것만. 추측·비유·인물의 생각은 넣지 마라.
- 값은 짧은 한국어로. 한 항목에 한 줄.
- 새로 나온 것이 없는 칸은 빈 객체로 둔다.
- **인물은 카드로 적는다.** 글에 드러난 칸만 채워라. 안 나온 칸은 빼라 -- 지어내지 마라.
  쓸 수 있는 칸: {" · ".join(CARD)}
- **관계 칸**에는 다른 인물과의 사이를 적어라 -- "요우의 옛 애인", "한나와 돈이 얽혔다".
  한 번 맺어진 관계는 저절로 풀리지 않는다.
- **몸 칸**에는 겉으로 드러나는 조건을 적어라 -- 안 들리는 귀, 안 크는 키, 떨리는 손.
- **속 칸**에는 그 사람이 늘 지고 다니는 것을 적어라 -- 다만 **행동으로 적어라**
  ("칭찬을 받으면 화제를 돌린다"). 감정 이름이나 진단명은 쓰지 마라.
- 한 번 적힌 것은 끝까지 그 사람의 것이다.
- **macguffin 에는 "다들 그것 때문에 움직이는데 정체가 안 밝혀진 것" 을 적어라.** 하나면
  족하다. 이미 적혀 있으면 새로 적지 마라 -- 맥거핀이 둘이면 둘 다 안 궁금해진다.
- **rules 에는 이 세계의 통칙을 적어라** -- 늘 그렇다고 말해진 것("겨울엔 배를 안 띄운다").
  한 번 세워진 통칙은 예외가 나와도 지워지지 않는다. 예외는 통칙을 정교하게 만든다.
- **folded 에는 그 통칙이 갈음한 낱낱의 사실 이름**을 적어라. 없으면 빈 목록.
- **open 에는 "던져지고 아직 안 닫힌 것" 을 적어라.** 확정된 사실이 아니라 미결이다 --
  묻고 답 안 한 질문, 한 약속, 진 빚, 기다리는 사람, 설명 안 된 물건, 감춘 것.
  글이 답을 준 것은 여기 적지 마라.
- **closed 에는 앞에서 열려 있다가 이번 글에서 답이 나온 것**의 이름을 적어라. 없으면 빈 목록.
- **지어낸 낱말은 words 에 뜻과 함께 적어라.** 사전에 없는 말이 나오고 거기 뜻이나 유래가
  달렸으면 그것이다. 한 번 적힌 말은 다음 덩어리에서도 같은 뜻으로 쓰인다.
- 말투 칸이 중요하다. 그 사람이 어떻게 말하는지 한 줄로 적어라
  (예: "존댓말인데 끝을 흐린다", "짧게 끊고 욕을 섞는다", "말이 길고 자꾸 되묻는다").
  **입버릇·감탄사가 있으면 그것까지 적어라** -- "놀라면 '어라랍쇼' 라고 한다",
  "말 시작 전에 '쓰읍' 하고 숨을 들이켠다". 그 사람이 다음에도 같은 소리를 내야 한다.

JSON 만 출력:
{{"people": {{"이름": {{"나이": "42", "직업": "양조장 정비공",
                     "말투": "짧게 끊는다. 욕을 섞는다", "과거": "..."}}}},
  "places": {{"장소": "어떤 곳인가 한 줄"}},
  "objects": {{"사물": "무엇인가 한 줄"}},
  "words": {{"꿉꿉하다": "눅눅한데 마음 쪽에 쓰는 말. 웅포 지방 말"}},
  "open": {{"요우가 기다리는 사람": "누구인지 아직 안 나왔다"}},
  "rules": {{"겨울 출항": "이 동네 사람들은 겨울에 배를 안 띄운다"}},
  "macguffin": {{"소금 공장": "다들 그것 때문에 움직이는데 정체는 아무도 모른다"}},
  "folded": ["통칙 하나로 갈음된 낱낱의 사실 이름들"],
  "closed": ["앞에서 열려 있다가 이번에 답이 나온 것"],
  "facts": {{"항목": "확정된 값"}},
  "time": ["시점 한 줄"]}}"""


# ---------------------------------------------------------------- 루프

def _after(book: dict, text: str) -> None:
    """덩어리를 채택한 뒤. 사건이 터졌으면 계수를 올리고 분량을 0 부터 다시 센다."""
    if book.get("_shock"):
        book["shocks"] = book.get("shocks", 0) + 1
        book["since"] = 0
    else:
        book["since"] = book.get("since", 0) + len(text)
    book["_shock"] = None


def step(book: dict, llm, log=None) -> dict:
    """덩어리 하나.

    두 가지를 본다. **모순은 원고를 죽이고, 리듬은 죽이지 않는다.**

      · 모순 -- 앞에서 쓴 것과 어긋나면 기각하고 다시 받는다. 끝내 못 풀면 멈춘다.
      · 리듬 -- 짧은 '-다' 가 줄줄이거나 대사가 없으면 숫자를 돌려주고 다시 받되,
        끝내 안 고쳐지면 **그중 제일 나은 것을 채택한다.** 취향 때문에 원고를 버릴 수는
        없다 -- 자유도가 이 모드의 전부다.
    """
    # **사건 차례인가.** 분량이 찼거나(약 2,000자), 원장이 부풀어 프롬프트가 무거워졌거나.
    # 첫 덩어리는 건너뛴다 -- 시작하자마자 남이 문을 부수고 들어오면 세계가 서기 전이다.
    book.setdefault("shocks", 0)
    book.setdefault("since", 0)
    book["_shock"] = None
    if book["chunks"]:
        D._log(f"[flow] 이번 세기 {_level(book):.2f} (기준 {book.get('drift', DRIFT)})")
    if book["chunks"] and SH.due(book["since"],
                                 len(brief(book["ledger"], now=len(book["chunks"]))),
                                 _level(book)):
        book["_shock"] = SH.draw(book.get("seed_id") or book["first"], book["shocks"])
        sk = book["_shock"]
        book["_last_shock"] = (f"{sk['who']} / {' / '.join(sk.get('hows') or [sk['how']])}"
                               f" / {sk['scale']}")
        D._log(f"[flow] 사건 {book['shocks'] + 1} -- {book['_shock']['who']} / "
               f"{book['_shock']['how']} / {book['_shock']['scale']}")

    # **한 번 쓰고, 한 번 고치고, 반드시 채택한다.**
    #
    # 예전에는 걸릴 때마다 원고를 통째로 다시 받았다 -- 결함이 넷이면 호출이 넷이고,
    # 새로 받은 원고는 또 다른 데서 걸렸다. 그리고 끝내 못 풀면 3,200자를 버렸다.
    # 이제는 다르다: 크게 한 번 쓰고, 걸린 문장을 **전부 모아 한 번에** 고쳐 달라고
    # 하고, 남은 것은 버리는 대신 장부에 적는다. 폐기는 없다.
    for attempt in range(1, 3):        # 두 번째는 답이 통째로 망가졌을 때만이다
        text = D._llm_for(llm, "narrator")(write_prompt(book)).strip()
        text, dropped = echo.trim(text, "".join(book["chunks"]))
        if dropped:
            D._log(f"[flow] 앞 글을 옮겨 적은 {dropped:,}자를 도려냈다")
        if len(text) >= 200:
            break
        D._log(f"[flow] 덩어리가 {len(text)}자로 왔다 -- 다시 받는다")
    if len(text) < 200:
        return {"status": "blocked", "chars": 0, "clashes": [],
                "why": f"덩어리가 {len(text)}자밖에 안 왔다"}

    def _read(t):
        """원고 하나를 읽어 원장 사본과 어긋난 것을 돌려준다."""
        try:
            delta = D.call_json(D._extractor(llm), extract_prompt(t), label="flow 추출")
        except ValueError as e:
            D._log(f"[flow] 추출 실패({e}) -- 원장 갱신 없이 간다")
            delta = {}
        probe = json.loads(json.dumps(book["ledger"]))
        return probe, _merge(probe, delta, at=len(book["chunks"]))

    probe, clashes = _read(text)

    # **고칠 것을 한 번에 다 보낸다.** 모순도 리듬도 같은 한 장에 담는다.
    items = mend_items(text, clashes, "".join(book["chunks"]))
    if items:
        D._log(f"[flow] 고칠 문장 {len(items)}개 -- 한 번에 고친다")
        try:
            fixed = D.call_json(D._extractor(llm), mend_prompt(items),
                                tries=1, label="flow 손질")
        except ValueError:
            fixed = {}
        mended, done = apply_patch(text, [x for x, _ in items], fixed)
        if done:
            D._log(f"[flow] 문장 {done}/{len(items)}개를 고쳤다")
            # 고쳤으면 원장을 다시 읽는다. 다시 읽어 더 나빠지면 안 고친 쪽을 쓴다.
            probe2, clash2 = _read(mended)
            if len(clash2) <= len(clashes):
                text, probe, clashes = mended, probe2, clash2

    # **남은 것은 버리지 않고 적는다.** 못 고친 곳을 원고와 함께 남겨 두면 나중에
    # 무엇이 안 되는지 볼 수 있다. 원고를 버리면 그것마저 안 남는다.
    # 사건 덩어리는 확산으로 재지 않는다 -- 거기서는 넓히고 회수하라고 시키지 않았으니
    # 그것으로 벌하지 않는다. 리듬만 본다(대사와 길이는 사건이든 아니든 지켜야 한다).
    left = (clashes + rhythm.check(text, want=_telllong(book), talk=_dialogue(book))
            + echo.check(text, "".join(book["chunks"])))
    if not book.get("_shock"):
        left += diffusion.check(text, book["ledger"], probe,
                                now=len(book["chunks"]), want=_talklong(book),
                                tune={"자": GENRE.tune(book.get("genre", ""), "자", {})})
    if left:
        _debt(book, len(book["chunks"]), left, path=book.get("_path"))
        # **원고 안에도 남긴다.** 파일은 사람이 보는 것이고, 이것은 다음 덩어리가
        # 읽는 것이다 -- 안 남기면 못 고친 것이 매번 처음부터 다시 못 고쳐진다.
        book.setdefault("owed", []).extend(_kind_of(c) for c in left)
        book["owed"] = book["owed"][-40:]
        D._log(f"[flow] 못 고친 {len(left)}건은 장부에 적어 둔다 (원고는 그대로 쓴다)")

    # **잰 값을 남긴다.** 다음 덩어리가 이것을 보고 방향을 잡는다 -- 남기지 않으면
    # 매번 처음부터 눈감고 흔드는 것이다.
    _remember(book, text)
    book["ledger"] = probe
    book["chunks"].append(text)
    _after(book, text)
    return {"status": "ok", "chars": len(text), "clashes": clashes}


def _remember(book: dict, text: str) -> None:
    """이 덩어리에서 실제로 나온 몫을 적어 둔다. 최근 것만 들고 있으면 된다."""
    m = rhythm.measure(text)
    book.setdefault("seen_tell", []).append(round(m.get("long", 0.0), 3))
    book.setdefault("seen_dlg", []).append(round(m.get("talk", 0.0), 3))
    mix = diffusion.measure(text, book["ledger"], book["ledger"]).get("mix")
    if mix and sum(mix):
        book.setdefault("seen_talk", []).append(round(mix[0] / sum(mix), 3))
    for k in ("seen_tell", "seen_talk", "seen_dlg"):
        if len(book.get(k, [])) > 24:
            book[k] = book[k][-24:]


# 자가 돌려준 문장에서 **갈래 이름**만 뽑는다. 문장을 통째로 쌓으면 세어도 뭉치지
# 않는다 -- 숫자가 매번 달라서 같은 결함이 다른 문장으로 보인다.
_KINDS = (
    ("짧은 '-다'", "짧은 '-다'"), ("내리", "같은 길이가 몰린다"), ("받아 올리는", "점층"),
    ("긴 문장이", "긴 문장"), ("대사가 전체", "대사 몫"), ("긴 대사", "긴 대사"),
    ("주고받", "주고받기"), ("세계에 더한", "세계 확장"), ("되돌아온", "앞엣것 회수"),
    ("규칙적인 자리", "박자표"), ("겹친다", "되풀이"), ("어긋난다", "모순"),
    ("같은 이름을", "이름 반복"), ("식은", "식은 소품"),
)


def _kind_of(msg: str) -> str:
    for key, name in _KINDS:
        if key in msg:
            return name
    return msg[:12]


def turned(book: dict) -> str:
    """**지난 덩어리에서 세계가 어떻게 달라졌는가.** 그 결과에서 이번 덩어리를 연다.

    지금까지 이야기를 끄는 것은 대사였다. 사람들이 말로 사이를 좁히고 말로 사정을
    설명하니, 읽으면 대화록이지 사건이 아니다. 원인은 구조에 있다 -- **덩어리와
    덩어리를 잇는 것이 꼬리 1,200자뿐**이라, 모델은 앞 문장에 이어 붙이는 것만 한다.
    앞 덩어리가 세계에 무엇을 **바꿔 놓았는지**는 아무도 안 알려 준다.

    그래서 바뀐 것을 짚어 준다. 새로 놓인 사람·장소·물건과 직전 사건을 대고,
    **이번 덩어리는 그 결과에서 시작하라**고 한다. 결과가 다음 원인이 되면 그것이
    사슬이고, 사슬이 곧 줄거리다."""
    if not book.get("chunks"):
        return ""
    now = len(book["chunks"])
    fresh = []
    for kind, label in (("people", "인물"), ("places", "장소"),
                        ("objects", "사물"), ("facts", "사실")):
        for name, rec in (book["ledger"].get(kind) or {}).items():
            age = rec.get("_age") if isinstance(rec, dict) else None
            if age is not None and now - age <= 1:
                fresh.append(f"{name}({label})")
    fresh = fresh[:6]
    last = book.get("_last_shock") or ""
    if not fresh and not last:
        return ""
    lines = ["[바뀐 것] **지난 덩어리가 세계에 남긴 것이다. 이번 덩어리는 그 결과에서 연다.**"]
    if fresh:
        lines.append("  · 새로 놓인 것 -- " + " · ".join(fresh))
    if last:
        lines.append(f"  · 직전에 벌어진 일 -- {last}")
    lines.append("  · **그래서 무엇이 달라졌는가**를 먼저 쓰고 거기서 이어라. 사람이 옮겨"
                 " 갔거나, 무엇이 없어졌거나, 누가 누구에게 빚을 졌거나, 사이가"
                 " 바뀌었거나. **말로 정리하지 말고 그 결과를 겪게 해라.**")
    lines.append("  · 그리고 이 덩어리도 세계를 **한 칸은 바꿔 놓고** 끝내라 -- 다음"
                 " 덩어리가 그것을 이어받는다. 아무것도 안 바뀌면 이야기가 선 것이다.")
    return "\n".join(lines)


def owed_brief(book: dict) -> str:
    """**갚지 않은 빚 하나.** 장부에 거듭 오른 갈래를 다음 덩어리에 얹는다.

    문장 손질로 고칠 수 있는 것은 세 갈래뿐인데 자는 열 갈래를 본다 -- 나머지 일곱은
    매번 장부에 적히고 끝났다(대사 몫 · 주고받기 · 세계 확장 · 점층 …). 재기만 하고
    고칠 길이 없으면 그 자는 장식이다.

    그래서 **다음 덩어리에서 갚게 한다.** 호출은 안 는다: 프롬프트 한 줄이다.
    한 건만 얹는다 -- 한꺼번에 시키면 안 지켜진다."""
    owed = book.get("owed") or []
    if len(owed) < 3:
        return ""
    tally: dict = {}
    for k in owed[-12:]:
        tally[k] = tally.get(k, 0) + 1
    top, cnt = max(tally.items(), key=lambda kv: (kv[1], kv[0]))
    if cnt < 2:
        return ""
    return (f"[갚을 것] **최근 덩어리들이 거듭 놓친 것 하나 -- {top}.** {cnt}번 걸렸다.\n"
            "이번 덩어리에서는 **이것 하나만** 확실히 해라. 나머지는 늘 하던 대로.")


def _debt(book: dict, at: int, left: list, path=None) -> None:
    """못 고친 것을 원고 옆 파일에 한 줄씩 쌓는다(JSONL). 폐기 대신 기록이다."""
    try:
        base = Path(path) if path else Path("drift.json")
        out = base.with_suffix(".debt.jsonl")
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"덩어리": at, "때": time.strftime("%m-%d %H:%M"),
                                "남은 것": left}, ensure_ascii=False) + "\n")
    except Exception:
        pass                    # 기록은 곁다리다 -- 여기서 원고를 죽이지 않는다


def _save(book: dict, path) -> None:
    if path:
        Path(path).write_text(json.dumps(book, ensure_ascii=False, indent=1),
                              encoding="utf-8")


# 연속으로 이만큼 실패하면 그때는 정말 멈춘다. 그 전까지는 기다렸다 다시 해 본다.
GIVE_UP = 8
BACKOFF = (20, 60, 120, 300, 600)      # 실패가 이어질 때 쉬는 시간(초)


def run(book: dict, llm, target: int, path=None, deadline=None) -> dict:
    """목표 글자 수까지 쓴다. **한 번 막혔다고 밤을 통째로 버리지 않는다.**

    예전엔 덩어리 하나가 막히면(모순을 못 풀거나 호출이 터지면) 그 자리에서 런이 끝났다.
    10만 자를 걸어 두고 잤는데 2,300자에서 서 있던 이유가 그것이다 -- 두 번째 덩어리
    뒤에 한 번 막혔고, 남은 일곱 시간을 아무것도 안 했다.

    막히는 이유는 대개 지나간다. 쿼터가 잠깐 마르거나, 망이 끊기거나, 모순 하나를 못
    푸는 것은 **다음 시도에서 대개 풀린다.** 그러니 기다렸다 다시 한다. 연속으로 여덟 번
    실패하면 그때는 정말 멈춘다 -- 그건 지나가는 문제가 아니다.
    """
    book["_path"] = str(path) if path else None    # 못 고친 것을 원고 옆에 적으려고
    _save(book, path)
    miss = 0
    while sum(len(c) for c in book["chunks"]) < target:
        if deadline and time.time() > deadline:
            D._log("[flow] 시간 상한 -- 여기서 멈춘다")
            break
        try:
            r = step(book, llm)
        except Exception as e:                       # 호출이 터져도 런은 안 죽는다
            r = {"status": "error", "why": f"{type(e).__name__}: {e}"[:120]}
        _save(book, path)

        if r["status"] == "ok":
            miss = 0
            continue

        miss += 1
        why = r.get("why") or "모순을 못 풀었다"
        if miss >= GIVE_UP:
            D._log(f"[flow] {miss}번 내리 실패 -- 멈춘다 ({why})")
            break
        wait = BACKOFF[min(miss - 1, len(BACKOFF) - 1)]
        D._log(f"[flow] 막혔다({why}) -- {wait}초 쉬었다 다시 한다 ({miss}/{GIVE_UP})")
        if deadline and time.time() + wait > deadline:
            D._log("[flow] 기다리면 시간 상한을 넘는다 -- 여기서 멈춘다")
            break
        time.sleep(wait)
    return {"chunks": len(book["chunks"]),
            "chars": sum(len(c) for c in book["chunks"])}


def text_of(book: dict) -> str:
    return "\n\n".join(book["chunks"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="novel/flow.json")
    ap.add_argument("--resume", default="")
    ap.add_argument("--read", default="")
    ap.add_argument("--chars", type=int, default=6000)
    ap.add_argument("--first", default=FIRST)
    ap.add_argument("--hours", type=float, default=12.0)
    ap.add_argument("--genre", default=GENRE.DEFAULT,
                    help=f"갈래 꾸러미 ({' · '.join(GENRE.names())}). 비우면 안 씌운다")
    ap.add_argument("--drift", type=float, default=DRIFT,
                    help="표류 계수 0~1. 낮출수록 급발진·사건이 줄어든다 (기본 1.0)")
    ap.add_argument("--matter", type=float, default=MATTER,
                    help="소재 축(갈래·매체)을 섞는 비율 0~1. 기본 0 -- 꺼져 있다")
    ap.add_argument("--trait", type=float, default=TRAIT,
                    help="설정(외현·내현)이 붙는 비율 0~1")
    ap.add_argument("--bond", type=float, default=BOND,
                    help="관계가 실리는 비율 0~1")
    ap.add_argument("--bridge", type=float, default=BRIDGE,
                    help="따로 있던 둘을 잇는 비율 0~1")
    ap.add_argument("--exception", type=float, default=EXCEPTION,
                    help="세워 둔 통칙을 깨는 비율 0~1")
    ap.add_argument("--doubt", type=float, default=DOUBT,
                    help="세워 둔 것의 지반을 흔드는 비율 0~1")
    ap.add_argument("--pov", type=float, default=POV,
                    help="시점을 옮기는 비율 0~1")
    a = ap.parse_args()

    if a.read:
        if not Path(a.read).exists():
            print(f"그런 파일이 없다: {a.read}\n"
                  f"  런은 **시작하자마자** 한 번 저장한다. 그러니 파일이 없다는 것은\n"
                  f"  아직 쓰는 중이라는 뜻이 아니라 **런이 시작도 못 했다**는 뜻이다.\n"
                  f"  살아 있는지, 왜 죽었는지 순서대로 봐라:\n"
                  f"    /usr/bin/pgrep -af 'novel/flow.py'\n"
                  f"    tail -40 logs/flow.log\n"
                  f"  (--out 에 준 경로와 --read 에 준 경로가 같은지도 확인해라)",
                  file=sys.stderr)
            return 1
        book = json.loads(Path(a.read).read_text(encoding="utf-8"))
        print(text_of(book))
        print(f"\n---\n덩어리 {len(book['chunks'])}개 · "
              f"{sum(len(c) for c in book['chunks']):,}자", file=sys.stderr)
        return 0

    path = a.resume or a.out
    book = (json.loads(Path(path).read_text(encoding="utf-8"))
            if a.resume and Path(a.resume).exists() else blank(a.first))

    # **첫 문장이 다르면 다른 소설이다.** 원장에는 앞 소설의 인물·장소·사물이 그대로
    # 남아 있어서, 그 위에 새 이야기를 얹으면 없던 사람이 걸어 들어오고 모순 검사도
    # 엉뚱한 것을 잡는다(실측 2026-09-05: "json 은 이야기가 바뀌면 초기화 되어야 하는데
    # 아직 이전 소설의 내역들이 그대로 남아있는 것 같아").
    #
    # 조용히 지우지는 않는다 -- 밤새 쓴 원고일 수 있다. 멈추고 무엇을 하라고 알려 준다.
    if a.resume and book.get("first") and book["first"] != a.first:
        print("첫 문장이 다르다 -- 이건 다른 소설이다. 이어 쓰지 않는다.\n"
              f"  원고에 박힌 첫 문장: {book['first'][:40]}...\n"
              f"  지금 주어진 첫 문장: {a.first[:40]}...\n"
              "  새 이야기를 쓰려면 --out 으로 새로 시작해라(scripts/drift.sh start).\n"
              "  이 원고를 이어 쓰려면 --first 를 빼거나 원고의 첫 문장을 그대로 줘라.",
              file=sys.stderr)
        return 2
    # **--drift 는 이어 쓰기에도 먹는다.** 뒤로 갈수록 부조리가 심해지면 중간에 낮춰서
    # 이어 갈 수 있어야 한다 -- 그러자고 원고를 버리게 하면 안 된다.
    # **설정은 원고가 아니라 코드가 정한다.**
    #
    # 계수를 원고에 저장해 두면 이어 쓸 때 그것을 쓴다. 그러면 코드 기본값을 고쳐도
    # 옛 원고는 옛 설정으로 계속 돈다 -- 밤새 고친 것이 하나도 안 걸린다(실측
    # 2026-09-05: "설정 json 도 초기화 하던가 옮겨줘야 해"). 저장은 무엇으로 썼는지
    # 남기려는 것이지 다음 런을 묶으려는 것이 아니다.
    #
    # 그래서 **매 런마다 인자(또는 기본값)로 덮어쓴다.** 원고를 이어 쓰되 설정은 지금
    # 것으로 간다. 옛 설정을 유지하고 싶으면 그 값을 인자로 주면 된다.
    for key, val in (("drift", a.drift), ("matter", a.matter),
                     ("trait", a.trait), ("bond", a.bond),
                     ("bridge", a.bridge), ("exception", a.exception),
                     ("doubt", a.doubt), ("pov", a.pov)):
        was = book.get(key)
        book[key] = max(0.0, min(1.0, val))
        if was is not None and was != book[key]:
            D._log(f"[flow] {key} {was} → {book[key]} (코드 기본값으로 맞춘다)")
    # 갈래도 같은 규칙 -- 매 런마다 인자로 덮어쓴다. 없는 갈래면 여기서 죽는다:
    # 조용히 기본값으로 물러서면 로맨스로 쓰는 줄 알고 밤새 다른 것을 쓴다.
    GENRE.get(a.genre)
    if book.get("genre") != a.genre:
        D._log(f"[flow] 갈래 {book.get('genre') or '(없음)'} → {a.genre or '(없음)'}")
    book["genre"] = a.genre
    D._log(f"[flow] 목표 {a.chars:,}자 · 지금 "
           f"{sum(len(c) for c in book['chunks']):,}자 · 표류 계수 {book['drift']}"
           f" · 소재 {book['matter']} · 설정 {book['trait']} · 관계 {book['bond']}"
           f" · 연결 {book['bridge']}")
    r = run(book, D.default_llm, a.chars, path, time.time() + a.hours * 3600)
    D._log(f"[flow] 끝 -- 덩어리 {r['chunks']}개 · {r['chars']:,}자 · {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
