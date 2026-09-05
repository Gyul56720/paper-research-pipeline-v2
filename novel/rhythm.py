"""문장 리듬을 **재서** 판정한다 -- 프롬프트로 부탁하지 않고 숫자로 잡는다.

2026-09-04 실측(flow.json, 8,489자)에 대한 사용자 평은 셋이었다:

    "끝이 -다. 이거 너무 단조롭게 재미 없다고.
     문장이 너무 짧고 리듬감이 없다고.
     대사가 너무 작위적이고 딱딱하다고"

프롬프트에는 이미 다 적혀 있었다. `style.narrator()` 의 [리듬] 항목이 "짧은 '-다' 문장이
두 번 이어지면 셋째에서 바꿔라" 라고 말하고, `flow.write_prompt()` 도 "장문과 단문을
섞어라 ... 지금 이 규칙이 가장 자주 깨진다" 라고 말한다. **그런데도 깨졌다.** 부탁으로는
안 된다는 뜻이다.

그래서 여기서는 잰다. 세 가지를 세고, 넘으면 그 숫자를 그대로 모델에게 돌려준다:

  · **'-다' 종결 비율**과 연속 횟수 -- 단조로움의 정체는 대개 이것이다
  · **긴 문장의 몫** -- 단문만 이어지면 리듬이 아니라 목록이 된다
  · **대사의 몫** -- 대사가 없으면 '-다' 를 깰 수단 하나가 통째로 빠진다

판정은 **무르게** 한다. 이건 취향의 영역이고, 자유도가 이 모드의 전부다. 그래서 리듬은
모순과 달리 **원고를 죽이지 않는다** -- 다시 써보라고 하되, 끝내 안 고쳐지면 제일 나은
것을 채택한다(`flow.step`). 기각이 잦으면 그 자유가 먼저 죽는다.
"""
from __future__ import annotations

import hashlib
import os
import re

# 문장 끝 '-다'. 닫는 따옴표나 괄호가 뒤에 붙어도 '-다' 로 센다.
#
# **'-다' 자체는 죄가 없다.** 기준으로 삼은 하루키 예문(style.py 의 [상황]/[점층])을 재보면
# 서술문의 86%가 '-다' 로 끝나고 여섯 문장이 내리 이어진다. 그런데 그건 단조롭지 않다 --
# 그 '-다' 중 71%가 마흔 자를 넘는 긴 문장이기 때문이다.
#
# 단조로움의 정체는 종결어미가 아니라 **길이**다. 짧은 '-다' 가 줄줄이 이어질 때 목록처럼
# 읽힌다. 그래서 여기서 세는 것은 '-다' 가 아니라 **짧은 '-다'** 다.
_DA = re.compile(r"다[.!?…”\"')\]]*$")
_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_QUOTE = re.compile(r"[\"“'']")

# 긴 문장의 기준. 하루키 예문("서른일곱 살이던 그때, 나는 좌석에 앉아 있었다. 그 거대한
# 비행기는 두터운 비구름을 뚫고 내려와, 함부르크 공항에 착륙을 시도하고 있었다.")의
# 둘째 문장이 마흔 몇 자다. 그 정도가 한 번씩 섞여야 리듬이 산다.
LONG = 45

# **점층** -- 앞 문장을 받아 한 단계 올리는 문장. 이것이 이 문체의 뼈다.
#
# 지금까지 프롬프트에만 적혀 있었다(style.py [점층]). 이 세션에서 확인된 것이 하나 있다면
# **재지 않는 것은 안 지켜진다**는 것이다. 그래서 센다.
#
# 요구량은 **분량에 비례한다.** 짧은 글에 세 번을 요구하면 그건 자가 아니라 억지다.
#
# 완벽한 판정은 못 한다. 점층인지 아닌지는 뜻의 문제라 기계가 못 본다. 그러나 한국어에서
# 앞 문장을 받아 올리는 문장은 **첫머리에 자국을 남긴다** -- 고쳐 말하거나("아니,",
# "정확히 말하자면"), 더 얹거나("게다가", "그것도"), 앞 것을 지시어로 받거나("그것은",
# "그 소리는"). 그 자국을 센다. 자국 없이 점층한 문장은 놓치지만, 그건 무른 자의 몫이다.
_CLIMB = (
    "아니", "아니,", "정확히", "그보다", "차라리", "오히려", "실은", "사실",
    "게다가", "더구나", "심지어", "그것도", "그리고 그", "그래서 그", "거기다",
    "그런데 그", "그래도", "다만", "물론", "적어도", "하필", "그중에서도",
    "말하자면", "굳이 말하자면", "요컨대", "결국", "무엇보다",
)
# 앞 문장을 지시어로 받는 첫머리. "그" + 한두 글자 명사 + 조사.
_ANAPHOR = __import__("re").compile(r"^(그것|그건|그게|그 [가-힣]{1,4}[은는이가도을를])")

# **하한만 두면 하한을 정확히 맞춘다.** 그것도 규칙적으로.
#
# 실측 2026-09-05: "단문 3에 장문 1이 너무 반복적으로 나온다." 긴 문장 15% 이상을
# 요구했더니 모델이 정확히 네 문장에 하나씩 길게 썼다 -- 자를 만족시키는 가장 싼 방법이
# 주기가 된 것이다. 균일한 15%는 균일한 0%만큼이나 단조롭다.
#
# 처음엔 **퍼짐**(표준편차÷평균)으로 재려 했는데 자가 거꾸로 나왔다 -- 기준으로 삼은
# 하루키 예문이 0.435 로 걸리고, 단문3+장문1 반복 패턴이 0.577 로 통과했다. 분산은
# 들쭉날쭉함을 재지 주기를 못 잡는다.
#
# 잡아야 하는 것은 **주기**다. 긴 문장이 어디에 오는지 자리를 적어 간격을 보면, 규칙적인
# 글은 그 간격이 다 같다(3, 3, 3, 3). 사람이 쓴 글은 안 그렇다(1, 4, 2, 6).
BEAT_MIN = 3            # 긴 문장이 이만큼은 나와야 주기를 따질 수 있다
# **거의 완벽하게 규칙적일 때만** 잡는다. 기준 문장(하루키)이 0.35 이고 단문3+장문1
# 반복이 0.00 이다. 그 사이에서 낮게 잡아야 기준을 안 벌하면서 박자표만 걸린다 --
# 자가 기준을 벌하면 자가 틀린 것이다.
BEAT_MIN_VAR = 0.15

# **긴 문장의 몫도 덩어리마다 흔든다.** 0.15 를 하한으로 두었더니 모델이 정확히 15%를,
# 그것도 규칙적인 자리에 놓았다 -- 그것이 '단문 셋에 장문 하나' 의 정체였다.
LONG_LO = float(os.environ.get("DRIFT_TELL_LONG_LO", "0.10"))
LONG_HI = float(os.environ.get("DRIFT_TELL_LONG_HI", "0.40"))
LONG_SLACK = float(os.environ.get("DRIFT_TELL_LONG_SLACK", "0.08"))
LOOK = int(os.environ.get("DRIFT_TELL_LOOK", "2"))
# 방향 탐색의 세기. 비례항은 흔들림을 잡고, 누적항은 정상 편차를 없앤다. 둘 다 크면
# 진동한다 -- 목표가 위아래로 튀면 원고도 같이 튄다.
# **대사가 원고의 절반이다.** 0.10 은 "대사가 아예 없지는 않게" 하는 바닥이었지 목표가
# 아니었다. 대사가 이야기를 밀고, 정보는 대사에 녹는다. 고정 하한을 두지 않고 구간을
# 조준한다 -- 어떤 대목은 거의 다 대사고, 어떤 대목은 서술이 더 많다.
TALK_LO = float(os.environ.get("DRIFT_TALK_LO", "0.35"))
TALK_HI = float(os.environ.get("DRIFT_TALK_HI", "0.65"))
TALK_SLACK = float(os.environ.get("DRIFT_TALK_SLACK", "0.10"))
P_GAIN = float(os.environ.get("DRIFT_P_GAIN", "0.6"))
I_GAIN = float(os.environ.get("DRIFT_I_GAIN", "1.2"))

# **몰리면 되민다.** 몫만 맞추면 앞쪽에 긴 것을 몰아 놓고 뒤를 전부 짧게 써도 통과한다.
# 짧은 것이 이만큼 이어지면 긴 것으로 끊고, 긴 것이 이만큼 이어지면 짧은 것으로 끊는다.
SHORT_RUN = int(os.environ.get("DRIFT_TELL_SHORT_RUN", "6"))
LONG_RUN = int(os.environ.get("DRIFT_TELL_LONG_RUN", "3"))

LIMITS = {
    "da":   0.62,   # **짧은** '-다' 가 이보다 많으면 단조롭다 (하루키 예문은 14%)
    "run":  4,      # 짧은 '-다' 가 이만큼 내리 이어지면 끊어야 한다
    "long": 0.15,   # 긴 문장이 이보다 적으면 목록처럼 읽힌다
    "climb": 5,     # **서술문 이만큼마다 하나**는 앞 문장을 받아 올려야 한다
    "talk": 0.10,   # 대사가 이보다 적으면 '-다' 를 깰 수단이 하나 빠진 것이다
}


def wave(seed: str, n: int, lo: float, hi: float, look: int = 2) -> float:
    """**덩어리마다 흔들리는 목표치.** 고정 하한은 그 자체가 주기가 된다 -- 하한을 두면
    모델은 하한을 정확히, 그리고 매번 맞춘다(실측: 짧은 '-다' 62%, 긴 대사 여덟 할).

    구간을 그대로 쓴다. 몇 개짜리 목록으로 끊어 두면 그 몇 개가 다시 주기가 된다.

    **한쪽 쏠림은 막는다.** 해시는 고르지만 고르다는 것은 짧게 보면 몰릴 수 있다는
    뜻이다 -- 낮은 값이 내리 나오면 그 대목이 통째로 한쪽으로 간다. 앞 look 개가 같은
    쪽이면 반대쪽으로 **접어 넣는다**(값을 버리지 않고 구간 안에서 뒤집는다 -- 버리면
    분포가 한쪽으로 깎인다).

    비교는 **확정된 값끼리** 한다. 날값끼리만 보면 앞에서 이미 뒤집혀 옮겨 온 자리를
    못 본다(실측: 그렇게 했더니 같은 쪽이 다섯 번 이어졌다)."""
    mid = (lo + hi) / 2

    def raw(i):
        h = hashlib.sha256(f"{seed}|{i}|{lo}|{hi}".encode()).digest()
        return lo + (hi - lo) * (int.from_bytes(h[:8], "big") % 10000) / 9999

    done: list[float] = []
    for i in range(max(0, n - look * 4), n + 1):
        v = raw(i)
        if len(done) >= look:
            side = [x > mid for x in done[-look:]]
            if all(side) and v > mid:
                v = lo + (hi - v)
            elif not any(side) and v <= mid:
                v = hi - (v - lo)
        done.append(min(hi, max(lo, v)))
    return done[-1]


def steer(seen: list, lo: float, hi: float, look: int = 3,
          fallback: float = None) -> float:
    """**방향 탐색.** 눈감고 흔드는 대신 **지난 덩어리에서 실제로 나온 값**을 보고 민다.

    wave() 는 해시로 목표를 흔든다 -- 원고를 안 보므로, 시킨 것과 나온 것이 어긋나도
    모른다. 목표를 여덟 할로 줬는데 넷 할이 나왔으면 다음 목표는 더 높아야 한다.
    그것이 이어지는 것이고, 수렴하는 것이다.

    미는 방향은 **모자란 쪽**이다. 최근 look 개의 평균이 구간의 가운데보다 낮으면
    위쪽을 겨누고, 높으면 아래쪽을 겨눈다. 얼마나 미는가는 어긋난 만큼이다 --
    조금 어긋났으면 조금만 민다(한 번에 되돌리면 그것이 다시 진동이 된다).

    잰 것이 없으면 fallback(없으면 가운데)으로 시작한다 -- 첫 덩어리는 밀 방향이 없다.
    """
    mid = (lo + hi) / 2
    if not seen:
        return mid if fallback is None else fallback
    recent = seen[-look:]
    avg = sum(recent) / len(recent)
    # 가운데에서 벗어난 만큼을 반대쪽으로 되돌린다. 계수 1.0 이면 대칭으로 튕겨
    # 진동하므로 절반만 민다 -- 되돌리되 넘어가지는 않게.
    # 비례항만 두면 **모자란 자리에서 멈춘다** -- 미는 힘과 안 따라오는 힘이 균형을
    # 이루는 지점이 가운데가 아니기 때문이다(실측: 0.25 를 겨눴는데 0.22 에서 섰다).
    # 그래서 **쌓인 어긋남**을 함께 민다. 계속 모자라면 목표가 계속 올라간다.
    debt = sum(mid - x for x in seen[-look * 4:]) / max(1, len(seen[-look * 4:]))
    want = mid + (mid - avg) * P_GAIN + debt * I_GAIN
    return min(hi, max(lo, want))


def aim(seed: str, n: int, seen: list, lo: float, hi: float,
        look: int = 3, jitter: float = 0.25) -> float:
    """**이번 덩어리의 목표.** 방향 탐색(steer)이 중심을 잡고, 흔들기(wave)가 폭을 준다.

    둘 중 하나만으로는 모자란다. 흔들기만 하면 원고를 안 보므로 시킨 것과 나온 것이
    어긋나도 모르고, 방향 탐색만 하면 값이 한 점으로 수렴해서 그 점이 다시 주기가 된다.
    중심은 모자란 쪽으로 옮기고, 그 둘레에서 흔든다."""
    base = steer(seen, lo, hi, look)
    span = (hi - lo) * jitter
    off = wave(f"{seed}|aim", n, -span, span, 2)
    return min(hi, max(lo, base + off))


def _lines(text: str) -> tuple[list[str], list[str]]:
    """서술문과 대사줄로 가른다."""
    talk, tell = [], []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _QUOTE.match(line):
            talk.append(line)
            continue
        for s in _SPLIT.split(line):
            s = s.strip()
            if s:
                tell.append(s)
    return tell, talk


def spread(nums) -> float:
    """길이의 퍼짐(변동계수). 대사 쪽에서 쓴다 -- 거기서는 이것으로 충분하다."""
    if len(nums) < 4:
        return 1.0
    mean = sum(nums) / len(nums)
    if mean <= 0:
        return 1.0
    var = sum((x - mean) ** 2 for x in nums) / len(nums)
    return (var ** 0.5) / mean


def beat(text: str) -> tuple[int, float]:
    """긴 문장이 **규칙적으로** 오는가. (긴 문장 수, 간격의 들쭉날쭉함) 을 돌려준다.

    간격이 다 같으면 0에 가깝다 -- 그것이 박자표다. 사람이 쓴 글은 간격이 제멋대로라
    이 값이 크다. 실측: 하루키 예문 0.63, 단문3+장문1 반복 0.00.
    """
    tell, _ = _lines(text)
    at = [i for i, x in enumerate(tell) if len(x) >= LONG]
    if len(at) < BEAT_MIN:
        return len(at), 1.0
    gaps = [b - a for a, b in zip(at, at[1:])]
    mean = sum(gaps) / len(gaps)
    if mean <= 0:
        return len(at), 0.0
    var = sum((g - mean) ** 2 for g in gaps) / len(gaps)
    return len(at), (var ** 0.5) / mean


_NUM = re.compile(r"\d[\d,]*")


def _numbers(s: str):
    out = []
    for t in _NUM.findall(s):
        try:
            out.append(int(t.replace(",", "")))
        except ValueError:
            pass
    return out


def numclimb(text: str) -> int:
    """**숫자로 하는 점층.** 이음말 없이 수만 늘어놓아도 점층이다 --
    "179번 탈락 · 87회 탈락 · 42회 탈락 · 14회 탈락" 처럼.

    실측: 직장물 표본은 글 전체가 이 방식으로 점층하는데 이음말 자로는 39개 중
    2개로 세어져 낙제였다. **자가 못 보는 것을 글의 잘못으로 돌리면 안 된다.**

    잇달아 나오는 서술문에서 수가 **한 방향으로** 움직이면 그만큼 점층으로 센다."""
    tell, _ = _lines(text)
    hits, run, prev = 0, 0, None
    for s in tell:
        ns = _numbers(s)
        cur = ns[0] if ns else None
        if cur is not None and prev is not None and cur != prev:
            run = run + 1 if run and (cur > prev) == (run > 0) else 1
            hits += 1
        else:
            run = 0
        prev = cur if cur is not None else prev
    return hits


def climb(text: str) -> int:
    """앞 문장을 받아 한 단계 올린 문장의 수."""
    tell, _ = _lines(text)
    n = 0
    for i, sent in enumerate(tell):
        if i == 0:
            continue
        head = sent.lstrip()
        if _ANAPHOR.match(head) or any(head.startswith(m) for m in _CLIMB):
            n += 1
    return n


def _clump(tell: list, want_long: bool) -> int:
    """같은 길이의 문장이 내리 몇 개 이어졌는가. **몰림을 재는 자다.**

    몫만 재면 앞쪽에 긴 것을 몰아 놓고 뒤를 전부 짧게 써도 통과한다 -- 몫은 맞는데
    읽으면 두 덩어리다. 리듬은 몫이 아니라 배치다."""
    run = best = 0
    for x in tell:
        if (len(x) >= LONG) == want_long:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def measure(text: str) -> dict:
    tell, talk = _lines(text)
    if not tell:
        return {"da": 0.0, "run": 0, "long": 0.0, "talk": 0.0, "n": 0}

    # 짧으면서 '-다' 로 끝나는 것만 센다. 긴 '-다' 는 리듬을 죽이지 않는다.
    da = [bool(_DA.search(s)) and len(s) < LONG for s in tell]
    run = best = 0
    for hit in da:
        run = run + 1 if hit else 0
        best = max(best, run)

    total = len(tell) + len(talk)
    return {
        "climb": climb(text) + numclimb(text),
        "beat": beat(text)[1],
        "da":   sum(da) / len(tell),
        "run":  best,
        "long": sum(len(s) >= LONG for s in tell) / len(tell),
        "srun": _clump(tell, False),        # 짧은 문장이 내리 이어진 최대
        "lrun": _clump(tell, True),         # 긴 문장이 내리 이어진 최대
        "talk": len(talk) / total if total else 0.0,
        "n":    len(tell),
    }


def spots(text: str) -> dict:
    """**어느 문장이 걸렸는지** 돌려준다 -- 전체를 다시 쓰지 않고 그 문장만 고치려고.

    check() 는 "64%가 짧은 '-다' 다" 라고 비율만 말한다. 그 말을 들은 모델은 원고를
    통째로 다시 뱉는다 -- 1,400자를 새로 만들어 두 문장을 고치는 셈이다. 자리를 짚어
    주면 그 문장만 받아 오면 된다.

    돌려주는 것은 {갈래: [걸린 문장, ...]} 이다. 문장 자체를 준다(번호가 아니라) --
    번호는 다시 쪼갤 때 어긋나지만 문장은 원문에서 그대로 찾을 수 있다."""
    tell, _ = _lines(text)
    short_da = [s for s in tell if _DA.search(s) and len(s) < LONG]
    out = {}
    m = measure(text)
    if m["n"] < 6:
        return out
    if m["da"] > LIMITS["da"]:
        # 넘긴 만큼만 고치면 된다 -- 전부 고치라고 하면 이번엔 반대로 넘어간다.
        need = len(short_da) - int(LIMITS["da"] * m["n"])
        out["da"] = sorted(short_da, key=len)[:max(1, need)]
    if m["run"] > LIMITS["run"]:
        run, run_at = [], []
        for s in tell:
            if _DA.search(s) and len(s) < LONG:
                run.append(s)
            else:
                if len(run) > LIMITS["run"]:
                    run_at += run[LIMITS["run"]:]
                run = []
        if len(run) > LIMITS["run"]:
            run_at += run[LIMITS["run"]:]
        if run_at:
            out["run"] = run_at
    if m["long"] < LIMITS["long"]:
        need = int(LIMITS["long"] * m["n"]) - sum(len(s) >= LONG for s in tell)
        out["long"] = sorted(short_da or tell, key=len, reverse=True)[:max(1, need)]
    return out


def check(text: str, want: float | None = None,
          talk: float | None = None) -> list[str]:
    """넘은 것만 사람 말로 돌려준다. 빈 목록이면 리듬은 괜찮다."""
    m = measure(text)
    if m["n"] < 6:                       # 너무 짧으면 통계가 의미 없다
        return []

    out = []
    if m["da"] > LIMITS["da"]:
        out.append(f"서술문 {m['n']}개 중 {m['da']:.0%}가 **짧은 '-다'** 로 끝난다. "
                   f"{LIMITS['da']:.0%} 아래로 내려라 -- 명사로 끝내거나, 말줄임으로 두거나, "
                   f"'-까/-지/-군/-는 것'으로 바꾸거나, 대사로 받아라")
    if m["run"] > LIMITS["run"]:
        out.append(f"짧은 '-다' 문장이 내리 {m['run']}번 이어진 자리가 있다. "
                   f"{LIMITS['run']}번을 넘기지 마라 -- 세 번째나 네 번째에서 생각을 붙이거나, "
                   f"대사를 넣거나, 문장을 끝내지 마라")
    # 이름을 want 로 두면 아래 긴 문장 목표(want 매개변수)를 덮어쓴다 -- 실측:
    # 목표를 안 줬는데도 "이 대목은 100%다" 가 나왔다.
    need = max(1, m["n"] // LIMITS["climb"])
    if m["climb"] < need:
        out.append(f"앞 문장을 받아 올리는 문장이 {m['climb']}개다. 서술문 {m['n']}개면 "
                   f"{need}개는 있어야 한다 -- **문장은 낱개로 서 있으면 안 된다.** 한 문장을 놓았으면 다음 "
                   f"문장이 그것을 **더 좁히거나, 더 키우거나, 뒤집어야** 한다. "
                   f"앞 문장을 고쳐 말하거나, 더 얹거나, 지시어로 받아라. "
                   f"그러다 끊고 다음으로 넘어가라")

    if m["beat"] < BEAT_MIN_VAR:
        out.append(f"긴 문장이 **규칙적인 자리**에 온다(들쭉날쭉함 {m['beat']:.2f}). "
                   f"비율은 맞췄는데 **주기가 됐다** -- 짧은 것 셋에 긴 것 하나를 규칙적으로 "
                   f"놓지 마라. 어떤 데서는 짧은 것이 다섯 번 이어지고, 어떤 데서는 긴 것이 "
                   f"둘 연달아 오고, 어떤 데서는 한 줄이 통째로 문단이 된다. **고르면 그것은 "
                   f"리듬이 아니라 박자표다.**")

    if want is None:
        if m["long"] < LIMITS["long"]:
            out.append(f"{LONG}자 넘는 문장이 {m['long']:.0%}뿐이다. "
                       f"{LIMITS['long']:.0%}는 넘겨라 -- 짧은 문장 서넛에 하나씩은 쉼표로 "
                       f"이어 붙인 긴 문장이 와야 한다. 단문만 이어지면 리듬이 아니라 목록이다")
    elif m["long"] < want - LONG_SLACK:
        out.append(f"{LONG}자 넘는 문장이 {m['long']:.0%}뿐이다. **이 대목은 {want:.0%}**다 -- "
                   f"쉼표로 이어 붙여 늘려라. 단문만 이어지면 리듬이 아니라 목록이다")
    elif m["long"] > want + LONG_SLACK and want <= 0.25:
        out.append(f"{LONG}자 넘는 문장이 {m['long']:.0%}다. **이 대목은 {want:.0%}**다 -- "
                   f"여기서는 짧게 끊어 가라. 매 대목을 길게 쓰면 그것도 한 가지 가락이다")

    # **몰림을 되민다.** 몫이 맞아도 앞뒤로 몰려 있으면 읽을 때는 두 덩어리다.
    if m["srun"] > SHORT_RUN:
        out.append(f"짧은 문장이 내리 {m['srun']}개 이어진 자리가 있다. "
                   f"{SHORT_RUN}개를 넘기지 마라 -- 그 자리를 **긴 문장 하나로 끊어라.** "
                   f"쉼표로 이어 붙여 딴 생각이든 눈에 들어온 것이든 붙이면 된다")
    if m["lrun"] > LONG_RUN:
        out.append(f"긴 문장이 내리 {m['lrun']}개 이어진 자리가 있다. "
                   f"{LONG_RUN}개를 넘기지 마라 -- 그 자리를 **짧은 문장 하나로 끊어라.** "
                   f"긴 것만 이어지면 숨 쉴 데가 없다")
    if talk is None:
        if m["talk"] < LIMITS["talk"]:
            out.append(f"대사가 전체 줄의 {m['talk']:.0%}뿐이다. "
                       f"{LIMITS['talk']:.0%}는 넘겨라 -- 사람을 만나게 하고 말을 시켜라")
    elif m["talk"] < talk - TALK_SLACK:
        out.append(f"대사가 전체 줄의 {m['talk']:.0%}뿐이다. **이 대목은 {talk:.0%}**다 -- "
                   f"사람을 만나게 하고 말을 시켜라. 설명하지 말고 **말하게 해라**: "
                   f"내력도 사정도 숫자도 대사 안에 녹는다")
    elif m["talk"] > talk + TALK_SLACK:
        out.append(f"대사가 전체 줄의 {m['talk']:.0%}다. **이 대목은 {talk:.0%}**다 -- "
                   f"여기서는 서술이 더 있어야 한다. 대사만 이어지면 희곡이지 소설이 아니다")
    return out


def score(text: str) -> float:
    """넘은 정도의 합. 낮을수록 좋다 -- 끝내 못 고쳤을 때 고르는 기준이다."""
    m = measure(text)
    return (max(0.0, BEAT_MIN_VAR - m["beat"]) * 0.5
            + max(0, max(1, m["n"] // LIMITS["climb"]) - m["climb"]) * 0.12
            + max(0.0, m["da"] - LIMITS["da"])
            + max(0, m["run"] - LIMITS["run"]) * 0.05
            + max(0.0, LIMITS["long"] - m["long"])
            + max(0.0, LIMITS["talk"] - m["talk"]))
