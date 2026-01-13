<?php
require_once '../config/database.php';

$series = $pdo->query("SELECT * FROM series ORDER BY year ASC, 
    CASE month 
        WHEN 'January' THEN 1 
        WHEN 'February' THEN 2 
        WHEN 'March' THEN 3 
        WHEN 'April' THEN 4 
        WHEN 'May' THEN 5 
        WHEN 'June' THEN 6 
        WHEN 'July' THEN 7 
        WHEN 'August' THEN 8 
        WHEN 'September' THEN 9 
        WHEN 'October' THEN 10 
        WHEN 'November' THEN 11 
        WHEN 'December' THEN 12 
    END ASC, series_name ASC")->fetchAll(PDO::FETCH_ASSOC);
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
                            <button class="btn btn-small btn-upload" data-id="<?= $s['id'] ?>" data-name="<?= htmlspecialchars($s['series_name']) ?>">Upload HTML</button>
                            <a href="matches.php?series_id=<?= $s['id'] ?>" class="btn btn-small btn-secondary">View Matches</a>
                        </td>
                    </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
        </div>
    </div>
        
        <div id="uploadModal" class="modal" style="display:none;">
            <div class="modal-content">
                <h3>Upload Rendered HTML</h3>
                <p id="uploadSeriesName"></p>
                <p class="help-text">Browser me series page kholo, Right Click > "Save Page As" > HTML Only save karo, phir yahan upload karo.</p>
                <form id="uploadForm" enctype="multipart/form-data">
                    <input type="hidden" id="uploadSeriesId" name="series_id">
                    <input type="file" name="html_file" id="htmlFile" accept=".html,.htm" required>
                    <div class="modal-actions">
                        <button type="submit" class="btn btn-primary">Parse Matches</button>
                        <button type="button" class="btn btn-secondary" onclick="closeModal()">Cancel</button>
                    </div>
                </form>
                <div id="uploadStatus"></div>
            </div>
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
        
        function closeModal() {
            document.getElementById('uploadModal').style.display = 'none';
        }
        
        document.querySelectorAll('.btn-upload').forEach(btn => {
            btn.addEventListener('click', function() {
                const seriesId = this.dataset.id;
                const seriesName = this.dataset.name;
                document.getElementById('uploadSeriesId').value = seriesId;
                document.getElementById('uploadSeriesName').textContent = 'Series: ' + seriesName;
                document.getElementById('uploadModal').style.display = 'flex';
                document.getElementById('uploadStatus').textContent = '';
                document.getElementById('htmlFile').value = '';
            });
        });
        
        document.getElementById('uploadForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(this);
            formData.append('action', 'parse_uploaded_html');
            
            const status = document.getElementById('uploadStatus');
            status.textContent = 'Processing...';
            status.className = '';
            
            fetch('scraper.php', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                status.textContent = data.message;
                status.className = data.success ? 'success' : 'error';
                if(data.success) {
                    setTimeout(() => {
                        closeModal();
                        location.reload();
                    }, 1500);
                }
            })
            .catch(error => {
                status.textContent = 'Error: ' + error;
                status.className = 'error';
            });
        });
    </script>
</body>
</html>
