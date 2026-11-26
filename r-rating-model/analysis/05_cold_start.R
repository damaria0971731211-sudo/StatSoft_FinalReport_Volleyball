# =============================================================================
# 冷啟動：新人加入平台後，要打幾局實力區間才夠窄？自報錯了多久會被修正？
#   1. 先模擬一間球館 40 人打 16 晚，用批次模型估出老球員的實力 (mu, v) 當作平台現況
#   2. 新人：真實實力 theta ~ N(0, 0.5^2)，自報程度依模擬規則產生（與實力相關 0.7）
#      四種情境（同一批新人、同一串比賽，只換先驗）：
#        自報準確／高估 2 級／低估 2 級／不填自報（先驗用全體分佈）
#   3. 新人每晚跟隨機 24 位老球員分 5 隊打 12 局，每打完一局就用線上更新
#   4. 看 95% 區間半寬、估計誤差、偏誤 隨局數的變化
# =============================================================================
source("R/rating_model.R"); source("R/simulate.R"); source("R/platform_model.R")
library(parallel)
N_NEW <- as.integer(Sys.getenv("N_NEW", "400")); N_NIGHTS <- 15

set.seed(7)
truth <- simulate_players(40, sigma = 0.5, tau = 1e-9, level_cor = 0.7)
hist <- simulate_league(truth, 16)
base <- fit_rating_model(hist, truth$players[, c("player", "level")], use_pairs = FALSE)
pool <- data.frame(player = base$ratings$player, mu = base$ratings$theta,
                   v = base$ratings$se^2, sets = 0L)
th_pool <- setNames(truth$players$theta_true - mean(truth$players$theta_true), truth$players$player)
beta <- base$beta; sigma <- base$sigma
sigma_all <- sqrt(var(pool$mu) + mean(pool$v))      # 不看自報時，全體實力的離散

one_newcomer <- function(i) {
  set.seed(9000 + i)
  th <- rnorm(1, 0, 0.5)
  z <- th / 0.5 * 0.7 + sqrt(1 - 0.7^2) * rnorm(1)
  lv <- min(5, max(1, round(3 + z)))
  # 先產生這位新人的整串比賽（四種情境共用）
  games <- list()
  for (night in seq_len(N_NIGHTS)) {
    mates <- sample(pool$player, 24)
    teams <- split(c("NEW", mates), rep(1:5, length.out = 25))
    for (s in 1:12) {
      ab <- sample(1:5, 2)
      if (!(1 %in% ab)) next                          # 新人在第 1 隊；只留新人有上場的局
      ta <- teams[[ab[1]]]; tb <- teams[[ab[2]]]
      st <- function(r) mean(ifelse(r == "NEW", th, th_pool[r]))
      tgt <- sample(c(20, 15), 1, prob = c(0.7, 0.3))
      sc <- play_set(plogis(st(ta) - st(tb)), tgt)
      games[[length(games) + 1]] <- list(ta = ta, tb = tb, a = sc[1], b = sc[2], night = night)
    }
  }
  priors <- list(自報準確 = c(beta * (lv - 3), sigma^2),
                 高估2級 = c(beta * (min(5, lv + 2) - 3), sigma^2),
                 低估2級 = c(beta * (max(1, lv - 2) - 3), sigma^2),
                 不填自報 = c(0, sigma_all^2))
  out <- list()
  for (nm in names(priors)) {
    st <- rbind(pool, data.frame(player = "NEW", mu = priors[[nm]][1], v = priors[[nm]][2], sets = 0L))
    rows <- data.frame(scenario = nm, id = i, theta = th, level = lv, set = 0, night = 0,
                       mu = st$mu[41], v = st$v[41])
    for (k in seq_along(games)) {
      gk <- games[[k]]
      st <- online_update(st, gk$ta, gk$tb, gk$a, gk$b)
      st[1:40, c("mu", "v")] <- pool[, c("mu", "v")]      # 老球員固定（只看新人的收斂）
      rows[nrow(rows) + 1, ] <- list(nm, i, th, lv, k, gk$night, st$mu[41], st$v[41])
    }
    out[[nm]] <- rows
  }
  do.call(rbind, out)
}
t0 <- Sys.time()
res <- do.call(rbind, mclapply(seq_len(N_NEW), one_newcomer, mc.cores = detectCores()))
cat("完成", N_NEW, "位新人，耗時", format(Sys.time() - t0), "\n")
res$err <- res$mu - res$theta
res$hw <- 1.96 * sqrt(res$v)
res$covered <- abs(res$err) < res$hw
sets_per_night <- mean(tapply(res$set[res$scenario == "自報準確"], res$id[res$scenario == "自報準確"], max)) / N_NIGHTS
saveRDS(list(res = res, beta = beta, sigma = sigma, sigma_all = sigma_all,
             sets_per_night = sets_per_night, N_NEW = N_NEW), "results/cold_start.rds")
s <- aggregate(cbind(hw, abs_err = abs(err), bias = err, covered) ~ scenario + set,
               data = res[res$set %in% c(0, 5, 10, 20, 30, 40, 60), ], FUN = mean)
print(s[order(s$scenario, s$set), ], digits = 3); cat("每晚約", sets_per_night, "局\n")
