# =============================================================================
# 公開資料：德國排球甲級聯賽（Volleyball Bundesliga）2013/14–2018/19 每局比分
# 來源：R 套件 volleystat（github.com/bozhinvi/volleystat，授權 CC0），
#       原始資料出自 volleyball-bundesliga.de 官方賽果
# 用途：
#  (1) 以「隊伍 = 一位球員」的方式套用同一個評分模型，在真實比分上做樣本外預測驗證
#  (2) 檢查「每球獨立」假設（預測的 deuce 比例 vs 實際）
#  (3) 借參數：真實聯賽隊伍實力的離散程度、每局分差分佈，作為模擬設定的參考
# =============================================================================
source("R/rating_model.R")
load("data/public/sets.rda"); load("data/public/matches.rda")

s <- as.data.frame(sets); m <- as.data.frame(matches)
s$key <- paste(s$league_gender, s$season_id, s$match_id)
m$key <- paste(m$league_gender, m$season_id, m$match_id)
home <- s[s$match == "home", ]; away <- s[s$match == "away", ]
g <- merge(home[, c("key", "league_gender", "season_id", "match_id", "set", "team_name", "pt_set")],
           away[, c("key", "set", "team_name", "pt_set")], by = c("key", "set"),
           suffixes = c("_h", "_a"))
g <- merge(g, unique(m[m$match == "home", c("key", "date_time")]), by = "key")
games_all <- data.frame(league = g$league_gender, season = g$season_id,
                        date = as.Date(g$date_time), set_no = g$set,
                        team_a = g$team_name_h, team_b = g$team_name_a,
                        score_a = g$pt_set_h, score_b = g$pt_set_a)
games_all <- games_all[order(games_all$league, games_all$season, games_all$date), ]
games_all$target <- ifelse(games_all$set_no == 5, 15, 25)
write.csv(games_all, "data/public/bundesliga_sets.csv", row.names = FALSE)

deuce_prob <- function(p, target) choose(2 * target - 2, target - 1) * p^(target - 1) * (1 - p)^(target - 1)

res <- list(); pred_all <- list(); sig <- list()
for (lg in unique(games_all$league)) for (ss in unique(games_all$season)) {
  d <- games_all[games_all$league == lg & games_all$season == ss, ]
  cut <- d$date[floor(nrow(d) / 2)]
  tr <- d[d$date <= cut, ]; te <- d[d$date > cut, ]
  te <- te[te$team_a %in% c(tr$team_a, tr$team_b) & te$team_b %in% c(tr$team_a, tr$team_b), ]
  fits <- list(
    eb   = fit_rating_model(tr, use_level = FALSE, use_pairs = FALSE),            # 經驗貝氏收縮
    flat = fit_rating_model(tr, use_level = FALSE, use_pairs = FALSE, sigma = 10) # 幾乎無收縮 ≈ MLE
  )
  sig[[length(sig) + 1]] <- data.frame(league = lg, season = ss, sigma = fits$eb$sigma,
                                       n_teams = nrow(fits$eb$ratings))
  for (nm in names(fits)) {
    pr <- t(sapply(seq_len(nrow(te)), function(i)
      predict_set(fits[[nm]], te$team_a[i], te$team_b[i], te$target[i])))
    pred_all[[length(pred_all) + 1]] <- data.frame(
      league = lg, season = ss, method = nm, p_rally = pr[, "p_rally"], p_set = pr[, "p_set"],
      win_a = as.integer(te$score_a > te$score_b), score_a = te$score_a, score_b = te$score_b,
      target = te$target,
      deuce = as.integer(pmax(te$score_a, te$score_b) > te$target))
  }
}
pred <- do.call(rbind, pred_all); sig <- do.call(rbind, sig)
ll <- function(y, p) -mean(y * log(p) + (1 - y) * log(1 - p))
summ <- do.call(rbind, lapply(split(pred, pred$method), function(x) data.frame(
  method = x$method[1], n_sets = nrow(x),
  log_loss = ll(x$win_a, x$p_set), brier = mean((x$p_set - x$win_a)^2),
  accuracy = mean((x$p_set > 0.5) == x$win_a))))
summ <- rbind(summ, data.frame(method = "coin", n_sets = nrow(pred) / 2, log_loss = log(2),
                               brier = 0.25, accuracy = 0.5))
# 每球獨立假設檢查：預測 deuce 次數 vs 實際（用 eb 模型、以 tie 前的機率近似）
eb <- pred[pred$method == "eb", ]
deuce_check <- data.frame(observed = sum(eb$deuce),
                          expected = sum(deuce_prob(eb$p_rally, eb$target) +
                                         0 * eb$p_rally), n = nrow(eb))
margin <- abs(games_all$score_a - games_all$score_b)[games_all$set_no < 5]
out <- list(summary = summ, pred = pred, sigma = sig, deuce = deuce_check,
            margin = margin, n_sets = nrow(games_all))
saveRDS(out, "results/bundesliga.rds")
print(summ); print(sig); print(deuce_check); print(summary(margin))
