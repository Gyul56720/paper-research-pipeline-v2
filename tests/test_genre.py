"""갈래 꾸러미 -- **갈아 끼운다.** 그리고 사건이 이야기를 끈다.

틀(리듬·확산·모순·급발진·말맛)은 갈래와 상관없이 그대로 돌아야 한다. 갈래가 바꾸는
것은 무엇을 놓느냐와 어느 쪽으로 기울이느냐 둘뿐이다 -- 그것이 여기서 고정하는 계약이다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from novel import flow, genre, shock as SH, wording as W              # noqa: E402

_bad = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        _bad.append(label)


print("[갈래] **갈아 끼운다** -- 이번엔 로맨스, 다음엔 다른 것")
ok(genre.get("") == {}, "갈래를 안 주면 아무것도 안 씌운다  ← 지금까지의 틀 그대로")
_died = False
try:
    genre.get("없는갈래")
except ValueError:
    _died = True
ok(_died, "모르는 갈래는 사실대로 실패한다  ← 조용히 물러서면 밤새 다른 것을 쓴다")
ok("romance" in genre.names(), f"로맨스가 있다 ({genre.names()})")

_g = genre.brief("romance", "씨", 3)
ok("[로맨스]" in _g, "머리표가 붙는다")
ok("이번 대목의 관계" in _g and "이번 대목에 일어날 수 있는 일" in _g,
   "관계와 사건을 하나씩 뽑아 준다")
ok("말로 진전되지 않는다" in _g,
   "관계는 말이 아니라 일로 움직인다고 못박는다  ← 지금은 대사로만 이야기가 간다")
ok(genre.brief("", "씨", 3) == "", "갈래가 없으면 빈 줄이다")
_rel = {tuple(SH._batch(genre.PACKS["romance"]["관계"], "씨|rel", i, "rel", 2))
        for i in range(10)}
ok(len(_rel) > 5, f"관계도 덩어리마다 다르다 ({len(_rel)}가지)")
_eve = {SH._batch(genre.PACKS["romance"]["사건"], "씨|eve", i, "eve", 1)[0]
        for i in range(10)}
ok(len(_eve) > 4, f"사건도 덩어리마다 다르다 ({len(_eve)}가지)")

print()
print("[저울] **소프트하게 올린다** -- 숫자를 박는 것이 아니라 구간을 옮긴다")
_base = [W._out_share("씨", n) for n in range(24)]
_rom = [W._out_share("씨", n, genre.tune("romance", "밖", None)) for n in range(24)]
ok(sum(_rom) / 24 > sum(_base) / 24 + 0.1,
   f"로맨스는 밖이 더 많다 (평균 {sum(_rom)/24:.0%} 대 {sum(_base)/24:.0%})")
ok(len(set(_rom)) > 15, f"그래도 매 덩어리 다르다 ({len(set(_rom))}가지)  ← 고정값이 아니다")
ok(min(_rom) < max(_rom) - 0.2, f"폭이 살아 있다 ({min(_rom):.0%}~{max(_rom):.0%})")
ok(genre.tune("", "밖", (0.25, 0.75)) == (0.25, 0.75), "갈래가 없으면 원래 구간이다")

print()
print("[사슬] **사건이 이야기를 끈다** -- 결과가 다음 원인이 된다")
print("      ← 덩어리를 잇는 것이 꼬리 1,200자뿐이라, 모델은 앞 문장에 이어 붙이는")
print("        것만 했다. 앞 덩어리가 세계에 무엇을 바꿔 놨는지는 아무도 안 알려 줬다.")
_bk = flow.blank(flow.FIRST)
ok(flow.turned(_bk) == "", "첫 덩어리에는 바뀐 것이 없다")
_bk["chunks"] = ["x" * 200]
_bk["ledger"]["people"] = {"도영": {"_age": 0, "나이": "42"}}
_bk["ledger"]["places"] = {"웅포": {"_age": 0}}
_bk["_last_shock"] = "낯선 사람 / 문을 부수고 들어온다 / 동네"
_t = flow.turned(_bk)
ok("도영(인물)" in _t and "웅포(장소)" in _t, "지난 덩어리가 새로 놓은 것을 짚는다")
ok("직전에 벌어진 일" in _t, "직전 사건도 짚는다")
ok("그 결과에서 연다" in _t, "이번 덩어리를 그 결과에서 열게 한다")
ok("말로 정리하지 말고 그 결과를 겪게 해라" in _t,
   "말로 정리하지 못하게 한다  ← 대사로 때우면 사건이 아니라 요약이다")
ok("한 칸은 바꿔 놓고" in _t, "이 덩어리도 세계를 바꾸고 끝내게 한다")

_old = flow.blank(flow.FIRST)
_old["chunks"] = ["x" * 200]
_old["ledger"]["people"] = {"도영": {"_age": -9, "나이": "42"}}
ok(flow.turned(_old) == "", "오래된 것은 안 짚는다  ← 매번 같은 이름을 대면 그것도 배경이다")

print()
print("[격리] **갈래는 틀을 안 건드린다**")
_p0 = flow.write_prompt(flow.blank(flow.FIRST))
_bk2 = flow.blank(flow.FIRST)
_bk2["genre"] = "romance"
_p1 = flow.write_prompt(_bk2)
for _sec in ("[문장]", "[리듬]", "[점층]", "[대사가 이야기다]", "[말맛]", "[확산]"):
    ok((_sec in _p0) == (_sec in _p1), f"{_sec} 는 갈래와 무관하다")
ok("[로맨스]" not in _p0, "갈래를 안 주면 로맨스가 안 실린다")
ok("[로맨스]" in _p1, "갈래를 주면 실린다")

print()
print("[직장물] **좋은 글을 튕기던 자를 고쳤다**")
print("      ← 표본(취준 직장물)을 우리 자로 재니 여덟 군데서 걸렸다. 대사 19%,")
print("        주고받기 5턴, 긴 대사 1개. 그런데 이 글은 서술이 이야기를 끈다 --")
print("        '대사가 절반' 은 자가 아니라 **갈래 가정**이었다.")
_s = (Path(__file__).resolve().parent / "sample_job.txt")
if _s.exists():
    _t = _s.read_text(encoding="utf-8")
    from novel import diffusion as F, rhythm as R                     # noqa: E402
    _base = F.check(_t, {}, {}, want=0.5)
    _tuned = F.check(_t, {}, {}, want=0.15,
                     tune={"자": genre.tune("job", "자", {})})
    ok(len(_tuned) < len(_base),
       f"직장물 저울로 재면 지적이 준다 ({len(_base)}건 → {len(_tuned)}건)")
    ok(not [c for c in R.check(_t, want=0.35, talk=0.2)],
       f"리듬은 이제 통과한다 ({R.check(_t, want=0.35, talk=0.2)})")
    _m = R.measure(_t)
    ok(R.numclimb(_t) >= 4,
       f"숫자로 하는 점층을 센다 ({R.numclimb(_t)}개)  ← 이음말만 세면 2개로 낙제였다")
    ok(_m["climb"] >= _m["n"] // R.LIMITS["climb"],
       f"점층 {_m['climb']}개 (필요 {_m['n'] // R.LIMITS['climb']}개)")

ok("job" in genre.names(), "직장물 꾸러미가 있다")
_j = genre.brief("job", "씨", 2)
ok("[직장물]" in _j, "머리표가 붙는다")
ok("이야기를 끄는 것은 대사가 아니라 서술이다" in _j, "무엇이 이야기를 끄는지 말한다")
ok("절차" in _j, "세계를 움직이는 것이 절차라고 말한다")
ok("이번 대목의 화법" in _j, "갈래 고유의 말버릇을 준다")
for _k in ("화자가 끼어든다", "자문자답", "화면을 그대로 옮긴다", "숫자로 점층한다"):
    ok(_k in genre.PACKS["job"]["화법"], f"표본에서 뽑아낸 화법: {_k}")
ok("이번 대목의 화법" not in genre.brief("romance", "씨", 2),
   "화법이 없는 갈래에는 안 실린다  ← 갈래마다 가진 것이 다르다")

_dlg = genre.tune("job", "대사", None)
ok(_dlg and _dlg[1] < 0.5, f"직장물은 대사 몫이 낮다 ({_dlg})")
ok(genre.tune("job", "자", {}).get("rally", 9) <= 3,
   "주고받기 요구도 낮다  ← 혼잣말이 대부분인 갈래다")
ok(genre.tune("romance", "자", {}) == {}, "로맨스는 자를 안 건드린다")

print()
if _bad:
    print(f"갈래: {len(_bad)}개 실패 -- {_bad}")
    raise SystemExit(1)
print("갈래: 갈아끼우기 · 저울 · 사슬 · 격리 -- 통과")
