<?php
require_once '../config/database.php';

function scrapeSeriesData() {
    global $pdo;
    
    $url = "https://www.cricbuzz.com/cricket-schedule/series/all";
    
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_USERAGENT, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language: en-US,en;q=0.5',
        'Connection: keep-alive',
    ]);
    
    $html = curl_exec($ch);
    
    if(curl_errno($ch)) {
        return ['success' => false, 'message' => 'cURL Error: ' . curl_error($ch)];
    }
    
    curl_close($ch);
    
    if(empty($html)) {
        return ['success' => false, 'message' => 'Empty response from website'];
    }
    
    $seriesCount = 0;
    
    preg_match_all('/<a[^>]*href="(\/cricket-series\/\d+\/[^"]+)"[^>]*>([^<]+)<\/a>/i', $html, $matches, PREG_SET_ORDER);
    
    $months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    preg_match_all('/(' . implode('|', $months) . ')\s+(\d{4})/', $html, $monthMatches);
    
    $currentMonth = !empty($monthMatches[1]) ? $monthMatches[1][0] : date('F');
    $currentYear = !empty($monthMatches[2]) ? $monthMatches[2][0] : date('Y');
    
    $processedUrls = [];
    
    foreach($matches as $m) {
        $seriesUrlPath = $m[1];
        $seriesName = trim($m[2]);
        
        if(empty($seriesName) || strlen($seriesName) < 3) continue;
        
        $baseUrl = preg_replace('/\/matches$/', '', $seriesUrlPath);
        if(isset($processedUrls[$baseUrl])) continue;
        $processedUrls[$baseUrl] = true;
        
        $seriesUrl = "https://www.cricbuzz.com" . $seriesUrlPath;
        if(strpos($seriesUrl, '/matches') === false) {
            $seriesUrl = rtrim($seriesUrl, '/') . '/matches';
        }
        
        $dateRange = '';
        
        $checkStmt = $pdo->prepare("SELECT id FROM series WHERE series_name = ?");
        $checkStmt->execute([$seriesName]);
        
        if($checkStmt->rowCount() == 0) {
            $stmt = $pdo->prepare("INSERT INTO series (month, year, series_name, date_range, series_url) VALUES (?, ?, ?, ?, ?)");
            $stmt->execute([$currentMonth, $currentYear, $seriesName, $dateRange, $seriesUrl]);
            $seriesCount++;
        }
    }
    
    return ['success' => true, 'message' => "Successfully scraped $seriesCount new series"];
}

function scrapeMatchesFromSeries($seriesId) {
    global $pdo;
    
    $stmt = $pdo->prepare("SELECT series_url FROM series WHERE id = ?");
    $stmt->execute([$seriesId]);
    $series = $stmt->fetch(PDO::FETCH_ASSOC);
    
    if(!$series) {
        return ['success' => false, 'message' => 'Series not found'];
    }
    
    $url = $series['series_url'];
    
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_USERAGENT, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    
    $html = curl_exec($ch);
    curl_close($ch);
    
    if(empty($html)) {
        return ['success' => false, 'message' => 'Empty response from website'];
    }
    
    $matchCount = 0;
    
    preg_match_all('/<a[^>]*href="(\/live-cricket-scores\/(\d+)\/[^"]+)"[^>]*>([^<]+)<\/a>/i', $html, $matches, PREG_SET_ORDER);
    
    $processedMatchIds = [];
    
    foreach($matches as $m) {
        $matchUrl = "https://www.cricbuzz.com" . $m[1];
        $matchId = $m[2];
        $matchTitle = trim($m[3]);
        
        if(empty($matchId) || isset($processedMatchIds[$matchId])) continue;
        $processedMatchIds[$matchId] = true;
        
        if(!empty($matchTitle) && strlen($matchTitle) > 2) {
            $checkStmt = $pdo->prepare("SELECT id FROM matches WHERE match_id = ? AND series_id = ?");
            $checkStmt->execute([$matchId, $seriesId]);
            
            if($checkStmt->rowCount() == 0) {
                $stmt = $pdo->prepare("INSERT INTO matches (series_id, match_id, match_title, match_url) VALUES (?, ?, ?, ?)");
                $stmt->execute([$seriesId, $matchId, $matchTitle, $matchUrl]);
                $matchCount++;
            }
        }
    }
    
    return ['success' => true, 'message' => "Successfully scraped $matchCount new matches"];
}

if(isset($_POST['action'])) {
    header('Content-Type: application/json');
    
    if($_POST['action'] === 'scrape_series') {
        echo json_encode(scrapeSeriesData());
    } else if($_POST['action'] === 'scrape_matches' && isset($_POST['series_id'])) {
        echo json_encode(scrapeMatchesFromSeries($_POST['series_id']));
    }
    exit;
}
?>
