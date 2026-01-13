<?php
require_once 'database.php';

$sql = "
CREATE TABLE IF NOT EXISTS series (
    id SERIAL PRIMARY KEY,
    month VARCHAR(50) NOT NULL,
    year VARCHAR(10) NOT NULL,
    series_name VARCHAR(255) NOT NULL,
    date_range VARCHAR(100),
    series_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    series_id INTEGER REFERENCES series(id) ON DELETE CASCADE,
    match_id VARCHAR(50),
    match_title VARCHAR(255),
    match_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
";

try {
    $pdo->exec($sql);
    echo "Tables created successfully!";
} catch(PDOException $e) {
    echo "Error creating tables: " . $e->getMessage();
}
?>
