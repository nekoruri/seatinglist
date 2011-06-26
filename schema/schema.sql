CREATE TABLE events (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    URL TEXT,
    seats_X TINYINT UNSIGNED NOT NULL,
    seats_Y TINYINT UNSIGNED NOT NULL,
    atnd_event_id INTEGER UNSIGNED DEFAULT NULL,
    owner_twitter_user_id INT UNSIGNED NOT NULL
) ENGINE=InnoDB;

CREATE TABLE enquete (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id INT UNSIGNED NOT NULL,
    short_title TEXT NOT NULL,
    question TEXT NOT NULL,
    opt1_text TEXT NOT NULL,
    opt1_color TEXT NOT NULL,
    opt2_text TEXT NOT NULL,
    opt2_color TEXT NOT NULL,
    opt3_text TEXT NOT NULL,
    opt3_color TEXT NOT NULL,
    opt4_text TEXT NOT NULL,
    opt4_color TEXT NOT NULL,
    opt5_text TEXT NOT NULL,
    opt5_color TEXT NOT NULL,
    opt6_text TEXT NOT NULL,
    opt6_color TEXT NOT NULL,
    opt7_text TEXT NOT NULL,
    opt7_color TEXT NOT NULL,
    opt8_text TEXT NOT NULL,
    opt8_color TEXT NOT NULL,
    opt9_text TEXT NOT NULL,
    opt9_color TEXT NOT NULL,
    opt10_text TEXT NOT NULL,
    opt10_color TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    INDEX ( event_id )
) ENGINE=InnoDB;

CREATE TABLE seats (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id INT UNSIGNED NOT NULL,
    seat_X TINYINT UNSIGNED NOT NULL,
    seat_Y TINYINT UNSIGNED NOT NULL,
    twitter_user_id INT UNSIGNED NOT NULL,
    registered_at DATETIME NOT NULL,
    unregistered_at DATETIME NULL,
    enquete_result_yaml TEXT NOT NULL DEFAULT '',
    is_enabled TINYINT(1) NOT NULL DEFAULT 1,
    is_machismo TINYINT(1) NULL
) ENGINE=InnoDB;

CREATE TABLE twitter_user_cache (
    user_id INT UNSIGNED PRIMARY KEY,
    screen_name VARCHAR(255) NOT NULL,
    profile_image_url TEXT
) ENGINE=InnoDB;

