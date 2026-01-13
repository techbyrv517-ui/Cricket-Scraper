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
    $currentMonth = '';
    $currentYear = '';
    
    $pattern = '/<div[^>]*class="[^"]*w-4\/12[^"]*font-bold[^"]*"[^>]*>([^<]+)<\/div>/i';
    preg_match_all($pattern, $html, $monthMatches, PREG_OFFSET_CAPTURE);
    
    $seriesPattern = '/<a[^>]*href="(\/cricket-series\/\d+\/[^"]+)"[^>]*title="([^"]+)"[^>]*>.*?<div[^>]*class="[^"]*text-ellipsis[^"]*"[^>]*>([^<]+)<\/div>.*?<div[^>]*class="[^"]*text-cbTxtSec[^"]*"[^>]*>([^<]*(?:<!--[^>]*-->)?[^<]*(?:<!--[^>]*-->)?[^<]*)<\/div>/is';
    preg_match_all($seriesPattern, $html, $seriesMatches, PREG_SET_ORDER | PREG_OFFSET_CAPTURE);
    
    $monthPositions = [];
    foreach($monthMatches[1] as $m) {
        $monthText = trim($m[0]);
        $parts = explode(' ', $monthText);
        if(count($parts) >= 2) {
            $monthPositions[] = [
                'position' => $m[1],
                'month' => ucfirst($parts[0]),
                'year' => $parts[1]
            ];
        }
    }
    
    $processedUrls = [];
    
    foreach($seriesMatches as $match) {
        $seriesUrlPath = $match[1][0];
        $seriesTitle = $match[2][0];
        $seriesName = trim($match[3][0]);
        $dateRangeRaw = $match[4][0];
        $seriesPosition = $match[0][1];
        
        $dateRange = preg_replace('/<!--[^>]*-->/', '', $dateRangeRaw);
        $dateRange = trim(preg_replace('/\s+/', ' ', $dateRange));
        
        $seriesMonth = 'January';
        $seriesYear = date('Y');
        
        foreach($monthPositions as $mp) {
            if($mp['position'] < $seriesPosition) {
                $seriesMonth = $mp['month'];
                $seriesYear = $mp['year'];
            } else {
                break;
            }
        }
        
        $baseUrl = preg_replace('/\/matches$/', '', $seriesUrlPath);
        if(isset($processedUrls[$baseUrl])) continue;
        $processedUrls[$baseUrl] = true;
        
        $seriesUrl = "https://www.cricbuzz.com" . $seriesUrlPath;
        if(strpos($seriesUrl, '/matches') === false) {
            $seriesUrl = rtrim($seriesUrl, '/') . '/matches';
        }
        
        if(!empty($seriesName)) {
            $checkStmt = $pdo->prepare("SELECT id FROM series WHERE series_url = ?");
            $checkStmt->execute([$seriesUrl]);
            
            if($checkStmt->rowCount() == 0) {
                $stmt = $pdo->prepare("INSERT INTO series (month, year, series_name, date_range, series_url) VALUES (?, ?, ?, ?, ?)");
                $stmt->execute([$seriesMonth, $seriesYear, $seriesName, $dateRange, $seriesUrl]);
                $seriesCount++;
            }
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
    
    preg_match_all('/<a[^>]*href="(\/live-cricket-scores\/(\d+)\/[^"]+)"[^>]*title="([^"]+)"[^>]*>/i', $html, $matches, PREG_SET_ORDER);
    
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

function scrapeAllMatches() {
    global $pdo;
    
    $allSeries = $pdo->query("SELECT id, series_name FROM series ORDER BY id")->fetchAll(PDO::FETCH_ASSOC);
    
    $totalMatches = 0;
    $seriesProcessed = 0;
    
    foreach($allSeries as $series) {
        $result = scrapeMatchesFromSeries($series['id']);
        if($result['success']) {
            preg_match('/(\d+)/', $result['message'], $m);
            $totalMatches += isset($m[1]) ? (int)$m[1] : 0;
        }
        $seriesProcessed++;
        usleep(500000);
    }
    
    return ['success' => true, 'message' => "Scraped $totalMatches matches from $seriesProcessed series"];
}

if(isset($_POST['action'])) {
    header('Content-Type: application/json');
    
    if($_POST['action'] === 'scrape_series') {
        echo json_encode(scrapeSeriesData());
    } else if($_POST['action'] === 'scrape_matches' && isset($_POST['series_id'])) {
        echo json_encode(scrapeMatchesFromSeries($_POST['series_id']));
    } else if($_POST['action'] === 'scrape_all_matches') {
        echo json_encode(scrapeAllMatches());
    }
    exit;
}
?>
