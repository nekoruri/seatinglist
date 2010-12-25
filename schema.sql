CREATE TABLE events (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    URL TEXT,
    seats_X TINYINT UNSIGNED NOT NULL,
    seats_Y TINYINT UNSIGNED NOT NULL,
    atnd_event_id INTEGER UNSIGNED DEFAULT NULL
) ENGINE=InnoDB;

CREATE TABLE seats (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id INT UNSIGNED NOT NULL,
    seat_X TINYINT UNSIGNED NOT NULL,
    seat_Y TINYINT UNSIGNED NOT NULL,
    twitter_user_id INT UNSIGNED NOT NULL,
    registered_at DATETIME NOT NULL,
    unregistered_at DATETIME NULL,
    is_enabled TINYINT(1) NOT NULL DEFAULT 1,
    is_machismo TINYINT(1) NULL
) ENGINE=InnoDB;

CREATE TABLE twitter_user_cache (
    user_id INT UNSIGNED PRIMARY KEY,
    screen_name VARCHAR(255) NOT NULL,
    profile_image_url TEXT
) ENGINE=InnoDB;

