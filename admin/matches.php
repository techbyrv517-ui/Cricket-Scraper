<?php
require_once '../config/database.php';

$seriesId = isset($_GET['series_id']) ? (int)$_GET['series_id'] : 0;

$seriesStmt = $pdo->prepare("SELECT * FROM series WHERE id = ?");
$seriesStmt->execute([$seriesId]);
$series = $seriesStmt->fetch(PDO::FETCH_ASSOC);

$matchesStmt = $pdo->prepare("SELECT * FROM matches WHERE series_id = ? ORDER BY created_at DESC");
$matchesStmt->execute([$seriesId]);
$matches = $matchesStmt->fetchAll(PDO::FETCH_ASSOC);
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Matches - <?= htmlspecialchars($series['series_name'] ?? 'Unknown') ?></title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div class="container">
        <header>
            <h1>Matches</h1>
            <p class="subtitle"><?= htmlspecialchars($series['series_name'] ?? 'Unknown Series') ?></p>
        </header>
        
        <div class="actions">
            <a href="index.php" class="btn btn-secondary">Back to Series</a>
        </div>
        
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Match Date</th>
                        <th>Match ID</th>
                        <th>Match Title</th>
                        <th>Match URL</th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach($matches as $m): ?>
                    <tr>
                        <td><?= $m['id'] ?></td>
                        <td><?= htmlspecialchars($m['match_date'] ?? '') ?></td>
                        <td><?= htmlspecialchars($m['match_id']) ?></td>
                        <td><?= htmlspecialchars($m['match_title']) ?></td>
                        <td><a href="<?= htmlspecialchars($m['match_url']) ?>" target="_blank">View Match</a></td>
                    </tr>
                    <?php endforeach; ?>
                    <?php if(empty($matches)): ?>
                    <tr>
                        <td colspan="5" style="text-align: center;">No matches found. Click "Scrape Matches" from the series page.</td>
                    </tr>
                    <?php endif; ?>
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
