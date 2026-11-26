# 讀取 Python 模擬器（/mnt/project-files/volley-sim）輸出的長格式資料，
# 轉成評分模型用的「每局一列」格式（team_a / team_b 以 ; 分隔）
read_volley_sim <- function(dir) {
  gp <- read.csv(file.path(dir, "data", "game_players.csv"), stringsAsFactors = FALSE)
  gm <- read.csv(file.path(dir, "data", "games.csv"), stringsAsFactors = FALSE)
  pl <- read.csv(file.path(dir, "data", "players.csv"), stringsAsFactors = FALSE)
  roster <- function(side) {
    x <- gp[gp$side == side, ]
    r <- tapply(x$player_id, x$game_id, function(v) paste(sort(v), collapse = ";"))
    r[gm$game_id]
  }
  games <- data.frame(date = gm$date, session = gm$session, game_id = gm$game_id,
                      team_a = as.character(roster("A")), team_b = as.character(roster("B")),
                      score_a = gm$score_a, score_b = gm$score_b,
                      target = gm$target_points, team_method = gm$team_method,
                      stringsAsFactors = FALSE)
  players <- data.frame(player = pl$player_id, level = pl$self_level,
                        position = pl$main_position, stringsAsFactors = FALSE)
  truth <- NULL
  tf <- file.path(dir, "truth", "players_truth.csv")
  if (file.exists(tf)) {
    tp <- read.csv(tf, stringsAsFactors = FALSE)
    ch <- read.csv(file.path(dir, "truth", "pair_chemistry.csv"), stringsAsFactors = FALSE)
    ch$pair <- pair_key(ch$player_1, ch$player_2)
    truth <- list(players = data.frame(player = tp$player_id, theta_true = tp$true_skill),
                  pairs = ch[, c("pair", "chemistry")])
  }
  list(games = games, players = players, truth = truth)
}
