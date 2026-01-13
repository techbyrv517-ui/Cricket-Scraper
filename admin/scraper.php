<?php
require_once '../config/database.php';

function scrapeSeriesData() {
    global $pdo;
    
    $url = "https://www.cricbuzz.com/cricket-schedule/series/all";
    
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_USERAGENT, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36');
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    
    $html = curl_exec($ch);
    
    if(curl_errno($ch)) {
        return ['success' => false, 'message' => 'cURL Error: ' . curl_error($ch)];
    }
    
    curl_close($ch);
    
    if(empty($html)) {
        return ['success' => false, 'message' => 'Empty response from website'];
    }
    
    $dom = new DOMDocument();
    @$dom->loadHTML($html);
    $xpath = new DOMXPath($dom);
    
    $seriesCount = 0;
    $currentMonth = '';
    $currentYear = '';
    
    $scheduleItems = $xpath->query("//div[contains(@class, 'cb-col-100')]");
    
    foreach($scheduleItems as $item) {
        $monthHeader = $xpath->query(".//div[contains(@class, 'cb-lv-grn-strip')]", $item);
        if($monthHeader->length > 0) {
            $monthText = trim($monthHeader->item(0)->textContent);
            $parts = explode(' ', $monthText);
            if(count($parts) >= 2) {
                $currentMonth = $parts[0];
                $currentYear = $parts[1];
            }
        }
        
        $seriesLinks = $xpath->query(".//a[contains(@href, '/cricket-series/')]", $item);
        
        foreach($seriesLinks as $link) {
            $seriesName = trim($link->textContent);
            $seriesUrl = "https://www.cricbuzz.com" . $link->getAttribute('href');
            
            if(strpos($seriesUrl, '/matches') === false) {
                $seriesUrl = rtrim($seriesUrl, '/') . '/matches';
            }
            
            $parent = $link->parentNode;
            $dateRange = '';
            $dateSpan = $xpath->query(".//span[contains(@class, 'cb-font-12')]", $parent);
            if($dateSpan->length > 0) {
                $dateRange = trim($dateSpan->item(0)->textContent);
            }
            
            if(!empty($seriesName) && !empty($currentMonth)) {
                $checkStmt = $pdo->prepare("SELECT id FROM series WHERE series_name = ? AND month = ? AND year = ?");
                $checkStmt->execute([$seriesName, $currentMonth, $currentYear]);
                
                if($checkStmt->rowCount() == 0) {
                    $stmt = $pdo->prepare("INSERT INTO series (month, year, series_name, date_range, series_url) VALUES (?, ?, ?, ?, ?)");
                    $stmt->execute([$currentMonth, $currentYear, $seriesName, $dateRange, $seriesUrl]);
                    $seriesCount++;
                }
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
    curl_setopt($ch, CURLOPT_USERAGENT, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36');
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    
    $html = curl_exec($ch);
    curl_close($ch);
    
    if(empty($html)) {
        return ['success' => false, 'message' => 'Empty response from website'];
    }
    
    $dom = new DOMDocument();
    @$dom->loadHTML($html);
    $xpath = new DOMXPath($dom);
    
    $matchCount = 0;
    
    $matchLinks = $xpath->query("//a[contains(@href, '/live-cricket-scores/')]");
    
    foreach($matchLinks as $link) {
        $matchUrl = "https://www.cricbuzz.com" . $link->getAttribute('href');
        $matchTitle = trim($link->textContent);
        
        preg_match('/\/live-cricket-scores\/(\d+)\//', $matchUrl, $matches);
        $matchId = isset($matches[1]) ? $matches[1] : '';
        
        if(!empty($matchId) && !empty($matchTitle)) {
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
