<?php
require_once '../config/database.php';

$series = $pdo->query("SELECT * FROM series ORDER BY year ASC, month ASC, series_name ASC")->fetchAll(PDO::FETCH_ASSOC);
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cricket Scraper - Admin Panel</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div class="container">
        <header>
            <h1>Cricket Scraper Admin Panel</h1>
        </header>
        
        <div class="actions">
            <button id="scrapeSeriesBtn" class="btn btn-primary">Scrape Series Data</button>
            <button id="scrapeAllMatchesBtn" class="btn btn-primary">Scrape All Matches</button>
            <span id="statusMessage" class="status-message"></span>
        </div>
        
        <div class="table-container">
            <h2>Series List</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Month</th>
                        <th>Year</th>
                        <th>Series Name</th>
                        <th>Date Range</th>
                        <th>Series URL</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="seriesTableBody">
                    <?php foreach($series as $s): ?>
                    <tr>
                        <td><?= $s['id'] ?></td>
                        <td><?= htmlspecialchars($s['month']) ?></td>
                        <td><?= htmlspecialchars($s['year']) ?></td>
                        <td><?= htmlspecialchars($s['series_name']) ?></td>
                        <td><?= htmlspecialchars($s['date_range']) ?></td>
                        <td><a href="<?= htmlspecialchars($s['series_url']) ?>" target="_blank">View</a></td>
                        <td>
                            <button class="btn btn-small scrape-matches" data-id="<?= $s['id'] ?>">Scrape Matches</button>
                            <a href="matches.php?series_id=<?= $s['id'] ?>" class="btn btn-small btn-secondary">View Matches</a>
                        </td>
                    </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        document.getElementById('scrapeSeriesBtn').addEventListener('click', function() {
            const btn = this;
            const status = document.getElementById('statusMessage');
            
            btn.disabled = true;
            btn.textContent = 'Scraping...';
            status.textContent = '';
            
            fetch('scraper.php', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'action=scrape_series'
            })
            .then(response => response.json())
            .then(data => {
                status.textContent = data.message;
                status.className = 'status-message ' + (data.success ? 'success' : 'error');
                btn.disabled = false;
                btn.textContent = 'Scrape Series Data';
                if(data.success) {
                    setTimeout(() => location.reload(), 1500);
                }
            })
            .catch(error => {
                status.textContent = 'Error: ' + error;
                status.className = 'status-message error';
                btn.disabled = false;
                btn.textContent = 'Scrape Series Data';
            });
        });
        
        document.getElementById('scrapeAllMatchesBtn').addEventListener('click', function() {
            const btn = this;
            const status = document.getElementById('statusMessage');
            
            btn.disabled = true;
            btn.textContent = 'Scraping All Matches...';
            status.textContent = 'This may take a few minutes...';
            status.className = 'status-message';
            
            fetch('scraper.php', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'action=scrape_all_matches'
            })
            .then(response => response.json())
            .then(data => {
                status.textContent = data.message;
                status.className = 'status-message ' + (data.success ? 'success' : 'error');
                btn.disabled = false;
                btn.textContent = 'Scrape All Matches';
            })
            .catch(error => {
                status.textContent = 'Error: ' + error;
                status.className = 'status-message error';
                btn.disabled = false;
                btn.textContent = 'Scrape All Matches';
            });
        });
        
        document.querySelectorAll('.scrape-matches').forEach(btn => {
            btn.addEventListener('click', function() {
                const seriesId = this.dataset.id;
                const button = this;
                
                button.disabled = true;
                button.textContent = 'Scraping...';
                
                fetch('scraper.php', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                    body: 'action=scrape_matches&series_id=' + seriesId
                })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    button.disabled = false;
                    button.textContent = 'Scrape Matches';
                })
                .catch(error => {
                    alert('Error: ' + error);
                    button.disabled = false;
                    button.textContent = 'Scrape Matches';
                });
            });
        });
    </script>
</body>
</html>
