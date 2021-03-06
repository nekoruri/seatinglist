package SeatingList::Model::DB;

use strict;
use warnings;

use base 'Mojo::Base';

use DBI;
use Data::Dumper;

__PACKAGE__->attr('dbh');

sub init {
    my $self = shift;
    my $config = shift;

    my $dbh = DBI->connect(
        $config->{db_dsn},
        $config->{db_username},
        $config->{db_password},
        { mysql_enable_utf8 => 1, mysql_auto_reconnect => 1 }
    );

    $self->dbh($dbh);

    return $self;
}

sub fetch_event_enquetes
{
    my $self = shift;
    my ( $event_id ) = @_;
    return if (!defined $event_id);

    my $sql = 'SELECT id, short_title, question, opt1_text, opt1_color, opt2_text, opt2_color, opt3_text, opt3_color, opt4_text, opt4_color, opt5_text, opt5_color, opt6_text, opt6_color, opt7_text, opt7_color, opt8_text, opt8_color, opt9_text, opt9_color, opt10_text, opt10_color FROM enquete WHERE event_id = ? ORDER BY created_at';
    my $sth = $self->dbh->prepare($sql);
    $sth->execute($event_id);
    my $enquetes = [];
    while (my $row = $sth->fetchrow_hashref) {
        push @$enquetes, $row;
    }
    return $enquetes;
}

sub generate_seats
{
    my $self = shift;
    my ( $event_id ) = @_;
    return if (!defined $event_id);

    my $sql = 'SELECT title, seats_X, seats_Y, atnd_event_id, description, URL, owner_twitter_user_id FROM events WHERE id = ?';
    my $sth = $self->dbh->prepare($sql);
    $sth->execute($event_id);

    my $event = $sth->fetchrow_hashref;
    my $seats_X = $event->{seats_X};
    my $seats_Y = $event->{seats_Y};

    # 座席表初期化
    # $seats->[seat_X][seat_Y] = { user_id => $user_id, ... }
    my $seats = [];
    foreach my $i ( 0 ... $seats_X-1 ) {
        $seats->[$i][$seats_Y-1] = undef;
    }

    $sql = 'SELECT seat_X, seat_Y, user_id, screen_name, profile_image_url, is_enabled, is_machismo, enquete_result_yaml FROM seats LEFT JOIN twitter_user_cache ON seats.twitter_user_id = twitter_user_cache.user_id WHERE event_id = ? AND unregistered_at IS NULL ORDER BY registered_at';
    $sth = $self->dbh->prepare($sql);
    $sth->execute($event_id);

    $event->{machismo} = 0;
    $event->{nomachismo} = 0;
    while (my @row = $sth->fetchrow_array) {
        # X,Yが同じものは新しい値で上書き
        if ( $row[5] ) {
            # 座席情報
            my $enquete_result = eval { YAML::Syck::Load($row[7]) };
            if ($@ || ref($enquete_result) ne 'HASH') {
                $enquete_result = {};
            }
            $seats->[$row[0]][$row[1]] = { user_id => $row[2], screen_name => $row[3], profile_image_url => $row[4], is_enabled => 1, is_machismo => $row[6], enquete_result => $enquete_result };
            # マッチョ集計
            if ( defined($row[6]) ) {
                if ( $row[6] == 1 ) {
                    $event->{machismo}++;
                } else {
                    $event->{nomachismo}++;
                }
            }
            # アンケート集計
            foreach my $enq ( keys %$enquete_result ) {
                $event->{enquete_summary}{$enq}{$enquete_result->{$enq}}++;
            }
        } else { 
            # 予約席
            $seats->[$row[0]][$row[1]] = { is_enabled => 0 };
        }
    }
    return ($event, $seats);
}

sub update_seat
{
    my $self = shift;
    my ( $user, $event_id, $seat_X, $seat_Y ) = @_;

    # 有効ならば、そのまま席を登録
    my $user_id = $user->{id};
    my $screen_name = $user->{screen_name};
    my $profile_image_url = $user->{profile_image_url};

    # 以前座っていた席(最新1件)の情報を取得
    my $sql = 'SELECT enquete_result_yaml, is_machismo FROM seats WHERE event_id = ? AND twitter_user_id = ? AND is_enabled = 1 AND unregistered_at IS NULL ORDER BY registered_at DESC LIMIT 1';
    my $sth = $self->dbh->prepare($sql);
    $sth->execute($event_id, $user_id);
    my ($enquete_result_yaml, $is_machismo ) = $sth->fetchrow_array;
    $enquete_result_yaml = '' if (!defined $enquete_result_yaml);

    # 以前座っていた席を全て無効化
    $sql = 'UPDATE seats SET unregistered_at = CURRENT_TIMESTAMP WHERE event_id = ? AND twitter_user_id = ?';
    $sth = $self->dbh->prepare($sql);
    $sth->execute($event_id, $user_id);

    # 座席情報を追加 (置き換えはしない)
    $sql = 'INSERT INTO seats ( event_id, seat_X, seat_Y, twitter_user_id, enquete_result_yaml, is_machismo, registered_at ) VALUES ( ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP )';
    $sth = $self->dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y, $user_id, $enquete_result_yaml, $is_machismo);

    # Twitterユーザ情報キャッシュを更新
    # user_idがプライマリキーなので既存レコードがあれば更新
    $sql = 'REPLACE INTO twitter_user_cache ( user_id, screen_name, profile_image_url ) VALUES ( ?, ?, ? )';
    $sth = $self->dbh->prepare($sql);
    $sth->execute($user_id, $screen_name, $profile_image_url);
}

sub disable_seat
{
    my $self = shift;
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'INSERT INTO seats ( event_id, seat_X, seat_Y, twitter_user_id, registered_at, is_enabled ) VALUES ( ?, ?, ?, 0, CURRENT_TIMESTAMP, 0 )';
    my $sth = $self->dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y);
}

sub enable_seat
{
    my $self = shift;
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'UPDATE seats SET unregistered_at = CURRENT_TIMESTAMP WHERE event_id = ? AND seat_X = ? AND seat_Y = ? AND is_enabled = 0 AND unregistered_at IS NULL';
    my $sth = $self->dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y);
}

sub remove_seat
{
    my $self = shift;
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'UPDATE seats SET unregistered_at = CURRENT_TIMESTAMP WHERE event_id = ? AND seat_X = ? AND seat_Y = ? AND is_enabled = 1 AND unregistered_at IS NULL';
    my $sth = $self->dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y);
}

sub machismo_seat
{
    my $self = shift;
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'UPDATE seats SET is_machismo = 1 WHERE event_id = ? AND seat_X = ? AND seat_Y = ? AND is_enabled = 1 AND unregistered_at IS NULL';
    my $sth = $self->dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y);
}

sub nomachismo_seat
{
    my $self = shift;
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'UPDATE seats SET is_machismo = 0 WHERE event_id = ? AND seat_X = ? AND seat_Y = ? AND is_enabled = 1 AND unregistered_at IS NULL';
    my $sth = $self->dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y);
}

# アンケート回答をYAMLにして保存
sub enquete_update
{
    my $self = shift;
    my ( $event_id, $user, $enquete_result ) = @_;

    my $enquete_result_yaml = eval { YAML::Syck::Dump($enquete_result) };

    my $sql = 'UPDATE seats SET enquete_result_yaml = ? WHERE event_id = ? AND twitter_user_id = ? AND is_enabled = 1 AND unregistered_at IS NULL';
    my $sth = $self->dbh->prepare($sql);
    $sth->execute($enquete_result_yaml, $event_id, $user->{id});
}

# 全てのイベントをID順に表示
sub search_all_events
{
    my $self = shift;
    my $sql = 'SELECT id, title FROM events ORDER BY id';
    my $sth = $self->dbh->prepare($sql);
    $sth->execute();
    my $events = [];
    while (my @row = $sth->fetchrow_array) {
        my $event = {
            id => $row[0],
            title => $row[1],
        };
        push @$events, $event;
    }
    return $events;
}

sub validate_event
{
    my $self = shift;
    my ($event_info) = @_;

    my %error;
    if ($event_info->{seats_X} =~ m/[^0-9]/ || $event_info->{seats_X} < 1) {
        # 必須、かつ数字以外が含まれる
        $error{seats_X} = '座席数は1以上の数値で入力してください。';
    }

    if ($event_info->{seats_Y} =~ m/[^0-9]/ || $event_info->{seats_Y} < 1) {
        # 必須、かつ数字以外が含まれる
        $error{seats_Y} = '座席数は1以上の数値で入力してください。';
    }

    if (!defined($event_info->{title}) || $event_info->{title} eq '') {
        # イベント名は必須
        $error{title} = 'イベント名は必ず入力してください。';
    }

    # 詳細(description), 関連URLはとりあえずvalidationなし

    if (defined($event_info->{title}) && $event_info->{title} eq '') {
        if ($event_info->{atnd_event_id} =~ m/[^0-9]/ || $event_info->{atnd_event_id} < 1) {
            # 数字以外が含まれる
            $error{atnd_event_id} = '座席数は1以上の数値で入力してください。';
        }
    }

    if (keys %error) {
        return \%error
    } else {
        return;
    }
}

# イベント情報の更新
sub update_event
{
    my $self = shift;
    my ( $event_id, $event ) = @_;
    return if (!defined $event_id);

    my $sql = 'SELECT title, seats_X, seats_Y, atnd_event_id, description, URL, owner_twitter_user_id FROM events WHERE id = ?';
    my $sth = $self->dbh->prepare($sql);
    $sth->execute($event_id);

    my $event_old = $sth->fetchrow_hashref;

    # 変更対象のカラム名
    my @cols = qw( title seats_X seats_Y atnd_event_id description URL );

    my @changed_cols;
    foreach my $col (@cols) {
        if (defined($event->{$col}) && $event_old->{$col} ne $event->{$col}) {
            push @changed_cols, $col;
        }
    }

    # 変更がある場合のみUPDATE
    if (@changed_cols) {
        $sql = 'UPDATE events SET '
                . join( ', ', map { "$_ = ?" } @changed_cols)
                . 'WHERE id = ?';
        my $sth = $self->dbh->prepare($sql);
        $sth->execute((map { $event->{$_} } @changed_cols),  $event_id);
    }
}

# イベント情報の更新
sub insert_event
{
    my $self = shift;
    my ( $event ) = @_;

    my $sql = <<'END_SQL';
INSERT INTO events
    ( title, seats_X, seats_Y, atnd_event_id, description, URL, owner_twitter_user_id)
    VALUES
    (     ?,       ?,       ?,             ?,           ?,   ?,                     ?)
END_SQL
    my @cols = qw( title seats_X seats_Y atnd_event_id description URL owner_twitter_user_id );
    my @params;
    foreach my $col (@cols) {
        push @params, defined($event->{$col}) ? $event->{$col} : '';
    }
    my $sth = $self->dbh->prepare($sql);
    $sth->execute(@params);

    # 挿入したイベントのIDを取得
    my $event_id = $sth->{mysql_insertid};
    return $event_id;
}

1;
