"""
從公開的 DataVolley 比賽紀錄（.dvw）算出模擬參數的基準值。

資料來源：openvolley/datavolley R 套件附的範例檔 inst/extdata/example_data.dvw
  https://raw.githubusercontent.com/openvolley/datavolley/master/inst/extdata/example_data.dvw
  內容：2015-01-25 斯洛維尼亞青年女子組決賽（Braslovče 3:0 Nova KBM Branik）。
  下載日期：2026-11-26。只用來計算彙總比例，不重新散布原檔。

用法：
    curl -sSLo example_data.dvw <上面的網址>
    python calibrate_from_datavolley.py example_data.dvw

2026-11-26 的輸出：
    rallies 127 sideout 0.520
    attacks 210  得分(#) 0.290 失誤(=) 0.071 被攔(/) 0.043
    serves 128   直接得分(#) 0.141 失誤(=) 0.141
    相鄰兩分間隔 中位數 29 秒
"""
import collections
import re
import statistics
import sys


def t2s(s):
    h, m, x = map(int, s.split("."))
    return h * 3600 + m * 60 + x


def main(path):
    lines = open(path, encoding="latin-1").read().split("\n")
    i = lines.index("[3SCOUT]")
    scout = [l.split(";") for l in lines[i + 1:] if l]
    serve = None
    rallies, gaps = [], []
    att, srv = collections.Counter(), collections.Counter()
    last = None
    for f in scout:
        code = f[0]
        if re.match(r"^[*a]\d\dS", code):          # 發球：記錄發球方與結果符號
            serve = code[0]
            srv[code[5]] += 1
        if re.match(r"^[*a]\d\dA", code):          # 攻擊
            att[code[5]] += 1
        m = re.match(r"^([*a])p(\d\d):(\d\d)", code)  # 得分列：*p 主隊得分、ap 客隊得分
        if m:
            if serve:
                rallies.append((serve, m.group(1)))
            t = t2s(f[7])
            if last is not None and t - last < 300:  # 排除局間休息
                gaps.append(t - last)
            last, serve = t, None
    n = len(rallies)
    so = sum(s != w for s, w in rallies) / n
    A, S = sum(att.values()), sum(srv.values())
    print(f"rallies {n} sideout {so:.3f}")
    print(f"attacks {A}  得分(#) {att['#']/A:.3f} 失誤(=) {att['=']/A:.3f} 被攔(/) {att['/']/A:.3f}")
    print(f"serves {S}   直接得分(#) {srv['#']/S:.3f} 失誤(=) {srv['=']/S:.3f}")
    print(f"相鄰兩分間隔 中位數 {statistics.median(gaps):.0f} 秒")


if __name__ == "__main__":
    main(sys.argv[1])
