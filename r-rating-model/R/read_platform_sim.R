# 讀取 Python 跨球館模擬器（volley-sim/platform）的輸出，轉成平台模型格式
read_platform_sim <- function(dir) {
  m <- read.csv(file.path(dir, "data", "matches.csv"), stringsAsFactors = FALSE)
  pl <- read.csv(file.path(dir, "data", "players.csv"), stringsAsFactors = FALSE)
  games <- data.frame(venue = m$venue_id, date = m$date, session = m$session, game_id = m$game_id,
                      team_a = gsub(" ", ";", m$players_a), team_b = gsub(" ", ";", m$players_b),
                      score_a = m$score_a, score_b = m$score_b, target = m$target_points,
                      stringsAsFactors = FALSE)
  games <- games[order(games$date, games$game_id), ]
  players <- data.frame(player = pl$player_id, home_venue = pl$venue_home, level = pl$self_level,
                        gender = pl$gender, years = pl$years_playing, stringsAsFactors = FALSE)
  truth <- NULL
  if (file.exists(file.path(dir, "truth", "players_truth.csv"))) {
    tp <- read.csv(file.path(dir, "truth", "players_truth.csv"), stringsAsFactors = FALSE)
    tv <- read.csv(file.path(dir, "truth", "venues_truth.csv"), stringsAsFactors = FALSE)
    truth <- list(players = data.frame(player = tp$player_id, theta_true = tp$true_theta,
                                       report_bias = tp$report_bias, cross = tp$cross_venue),
                  venues = tv)
  }
  list(games = games, players = players, truth = truth)
}
