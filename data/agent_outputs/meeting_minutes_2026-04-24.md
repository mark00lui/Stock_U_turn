# CTA Pipeline 改革會議紀要 — 2026-04-24

## 與會人員
- **Chief Strategist** (主持 / 仲裁人)
- **Data RD** — 數據 API 可行性、資本額分佈
- **Signal Analyst** — 量能訊號統計穩定性
- **Industry Analyst** — 產業 alpha 覆蓋率
- **Trader** — 實戰流動性、倉位風險

---

## 議程
- **A. Universe 改革**：現行「TOP1000 by trade value」→ 改為「資本額 ≥ NT$30億 (上市+上櫃+KY)」
- **B. Volume Gate 改革**：現行「20日均量 × 1.2x」→ 改為「6月(120日)均量基底 + 成交金額下限」

---

## 各方論點摘要

### A. Universe 篩選

| 立場 | 提案 | 核心理由 |
|------|------|----------|
| **老闆原意** | 資本額 ≥ 30億 | 體質過濾、體制完整 |
| **Data RD** | 資本額 ≥ 50億 (238檔) | 30億過鬆 + TPEx 代表性不足 |
| **Industry** | 市值 ≥ 100億 (或下修資本額至 10–15億) | **30億會誤殺世芯-KY(7.6億)、信驊(2.3億)、M31(4.1億)、譜瑞-KY(6.8億)、穎崴(7.7億)** 這批 2024–2026 台股 alpha 冠軍 IC 設計/AI ASIC 族群 |
| **Trader** | 資本額 30億 **AND** 20日日均值 3億 **AND** 6月日均值 2億 | 體質 + 流動性雙把關，防堵「大牛股」 |

**關鍵衝突點**：資本額切點越高，體質越好但會砍掉小資本高市值的 AI ASIC 冠軍股；切點越低，則需流動性補強。

### B. Volume Gate (量能閘)

| 立場 | 主閘 | 次/輔閘 | 核心理由 |
|------|------|---------|----------|
| **Signal Analyst** | 今日/MA120 ≥ 1.5x | 今日/MA20 ≥ 1.0x；MA120 日值 ≥ 3億；當日日值 ≥ 1.5億；MIN_HISTORY 提至 140 | 統計穩定、抓「沉睡甦醒」、抗洗盤 |
| **Trader** | 今日/MA20 ≥ 1.2x | 今日量 ≥ MA120 × 0.8 (絕對量地板)；今日日值 ≥ 1億 | 即時性優先，爆量第一天不能被稀釋成 1.5x 擋住 |

**關鍵衝突點**：以 6月為主會讓強勢多頭股每天都過門檻變噪音、且錯過噴出行情 Day 1；以 20日為主則縮量陷阱和樣本不穩。

---

## 仲裁結論

### A1. Universe 最終公式 (混合派 — Trader 基礎 + Industry 救援)

採用**複合 OR 條件**，讓資本額小但流動性強的 AI ASIC 冠軍股不被誤殺：

```
universe = (
    (資本額 ≥ 30億 AND 20日日均成交值 ≥ 1億)    # 老闆原意 + 流動性底線
    OR
    (市值 ≥ 150億 AND 20日日均成交值 ≥ 3億)      # 小資本高市值高流動救援
)
AND 排除 ETF / DR股 / 全額交割 / 處置股
AND 股價 ≥ NT$50 (延續現行品質基線)
AND 6月日均成交值 ≥ 1億                           # 絕對流動性地板
```

**預估 universe 規模**：約 350–450 檔（需 backtest 驗證）

### A2. 仲裁理由
1. **尊重老闆原意** — 30億資本額作為主軸保留，體制門檻不降低
2. **救回 alpha 來源** — 第二條 OR 專門救「小資本高市值」的 IC 設計股（世芯/信驊/譜瑞/穎崴/M31 的市值都遠超 150億）
3. **拒絕 Data RD 的 50億** — 238 檔太窄、且砍掉多數 TPEx 成長股
4. **拒絕 Industry 的純市值** — 市值每日變動不穩定，不適合作為唯一過濾器
5. **採用 Trader 的流動性雙把關** — 20日(實時) + 6月(地板) 防堵大牛股
6. **白名單暫緩** — 有 OR 條件後白名單冗餘；若日後發現漏網 alpha 股再補

### B1. Volume Gate 最終公式 (折衷派 — 20日主閘 + 6月地板 + 日值雙閘)

採用 **Trader 的主次順序 + Signal Analyst 的統計嚴謹**：

```python
# Gate 1 — 量能比率 (主閘，即時性)
today_vol / MA20 ≥ 1.2x

# Gate 2 — 絕對量地板 (6月基底防幻覺)
today_vol ≥ MA120 × 0.8

# Gate 3 — 成交金額絕對下限
today_daily_value ≥ NT$1.5億   # 當日硬底
MA20_daily_value  ≥ NT$3億      # 20日穩定底 (沿用現行)
MA120_daily_value ≥ NT$1.5億    # 6月地板 (新增)

# Gate 4 — 樣本充足性
MIN_HISTORY_DAYS = 140          # 確保 MA120 可算
```

### B2. 仲裁理由
1. **實戰即時性優先** — Trader 論點成立：爆量第一天若被 1.5x 擋住，策略價值折半
2. **保留 Signal Analyst 的 6月地板** — 作為「絕對量」守門員，擋掉縮量陷阱與連續鈍化的假訊號
3. **MIN_HISTORY 140 天** — 同意 Signal Analyst 提升，換取 MA120 穩定性（現行 60 天太短）
4. **不採 1.5x 主閘** — Signal Analyst 的 1.5x 太嚴，會讓訊號數量 -25% 過頭，破壞 min-stars=4 的訊號密度

---

## Go / No-Go 決議

### 決議：**Conditional Go — 先 A/B Backtest 才上線**

| 項目 | 決議 | 說明 |
|------|------|------|
| Universe 改革 (A) | 🟡 **Go with A/B test** | 因重疊僅 149/891 檔，本質性變更必須先做歷史回測 |
| Volume Gate 改革 (B) | 🟡 **Go with A/B test** | 與 A 同時跑 A/B，確認勝率/Sharpe 不倒退 |
| 上線時機 | A/B backtest 通過後的下一個交易日 | 預計 2026-04-28 (下週一) |
| 回退條件 | 新版連續 3 日無訊號、或 7 日勝率 < 40% | 立即切回舊版 config |

---

## 實作路線圖

| Step | 任務 | 責任人 | 預計耗時 | 優先級 |
|------|------|--------|----------|--------|
| 1 | 新增 `fetch_capital.py` (TWSE + TPEx + KY 統一入口，7天 cache) | Data RD | 3 小時 | P0 |
| 2 | 新增 `fetch_market_cap.py` (日收盤 × 流通在外股數)，作 OR 條件第二支柱 | Data RD | 2 小時 | P0 |
| 3 | 改 `fetch_universe.py` — 套用複合 OR 公式 + 流動性過濾 | Data RD | 2 小時 | P0 |
| 4 | 改 `config.py` — 新增 `MIN_CAPITAL`, `MIN_MARKET_CAP`, `MIN_AVG_VALUE_120D`, `VOL_FLOOR_RATIO_120D`，`MIN_HISTORY_DAYS=140` | Chief Strategist | 0.5 小時 | P0 |
| 5 | 改 `signals_momentum.py` — 加入 Gate 2 / Gate 3 的 6月地板邏輯 | Signal Analyst | 1.5 小時 | P0 |
| 6 | 改 `signals_breakout.py` — 同步量能邏輯 | Signal Analyst | 1.5 小時 | P0 |
| 7 | 同步 `backtest.py` 內複製的 `_momentum_score` / `_breakout_score` | Signal Analyst | 1 小時 | P0 |
| 8 | **A/B Backtest** — 2024-01 ~ 2026-04 期間，比對：舊 universe×舊 gate / 新 universe×舊 gate / 新 universe×新 gate | Signal Analyst + Trader | 3 小時 | P0 |
| 9 | 產出 A/B 比對報告 `data/agent_outputs/ab_backtest_2026-04-24.md` (勝率、Sharpe、MDD、訊號數量) | Chief Strategist | 1 小時 | P0 |
| 10 | 老闆確認 → merge to main → 下一個交易日啟用 | 老闆 | — | — |

**總預計耗時**：約 15.5 小時工程時間 + 老闆 review，週末可完成。

---

## 風險與回退

### 主要風險
1. **訊號數量斷崖** — universe 從 891 → ~400，訊號密度可能 -50%，某日可能零訊號
   - **緩解**：維持 min-stars=4 不變，接受「寧缺勿濫」原則；若 5 日平均訊號 < 1 檔，調降 Gate 2 的 0.8x 至 0.6x
2. **市值資料源穩定性** — 市值計算需每日更新流通股數
   - **緩解**：Data RD 用 yfinance `sharesOutstanding` 欄位並設 fallback 至 TWSE API
3. **OR 條件造成 universe 忽大忽小** — 市值隨行情波動，可能今天 400 檔明天 450 檔
   - **緩解**：市值取 20日均值，避免單日抖動
4. **A/B backtest 結果不如預期** — 新方案可能勝率反而下降
   - **緩解**：若 Sharpe < 舊版 90%，只上 Volume Gate 不改 Universe；或只改 Universe 不改 Gate，分階段上線

### 回退計畫
- 保留 `config.py` 舊參數區塊加 `# LEGACY 2026-04-22` 註解
- Git tag `pre-universe-reform-2026-04-24` 作為回退錨點
- 若上線後 3 日無訊號或 7 日勝率 < 40%，執行 `git revert` 一鍵回退

---

## 附註：被救援名單驗證 (抽樣)

| 股票 | 資本額 | 市值 (估) | 20日日均值 (估) | 新 universe 是否入選 |
|------|--------|-----------|-----------------|----------------------|
| 世芯-KY (3661) | 7.6億 | 1800億+ | 30億+ | ✅ (OR 第二條) |
| 信驊 (5274) | 2.3億 | 1200億+ | 15億+ | ✅ (OR 第二條) |
| M31 (6643) | 4.1億 | 300億+ | 5億+ | ✅ (OR 第二條) |
| 譜瑞-KY (4966) | 6.8億 | 600億+ | 8億+ | ✅ (OR 第二條) |
| 穎崴 (6515) | 7.7億 | 500億+ | 6億+ | ✅ (OR 第二條) |
| 中砂 (1560) | 6.5億 | 200億+ | 3億+ | ✅ (OR 第二條) |
| 博智 (8155) | 5.6億 | 180億+ | 4億+ | ✅ (OR 第二條) |

**結論**：Industry Analyst 擔心的 alpha 來源全數被第二條 OR 救回。

---

*會議結束 — 2026-04-24 15:25 GMT+8*
*下一步：等老闆拍板 → 進入實作階段*
