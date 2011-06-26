ALTER TABLE events ADD COLUMN owner_twitter_user_id INT UNSIGNED;
UPDATE events SET owner_twitter_user_id = 0;
ALTER TABLE events MODIFY COLUMN owner_twitter_user_id INT UNSIGNED NOT NULL;

