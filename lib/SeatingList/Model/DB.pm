package SeatingList::Model::DB;

use strict;
use warnings;

use base 'Mojo::Base';

use DBI;

__PACKAGE__->attr('dbh');

sub init {
    my $self = shift;
    my $config = shift;

    my $dbh = DBI->connect(
        $config->{db_dsn},
        $config->{db_username},
        $config->{db_password},
        { mysql_enable_utf8 => 1 }
    );

    $self->dbh($dbh);

    return $self;
}

sub generate_seats
{
    my $self = shift;
    my ( $event_id ) = @_;

    my $sql = 'SELECT title, seats_X, seats_Y FROM events WHERE id = ?';
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

    $sql = 'SELECT seat_X, seat_Y, user_id, screen_name, profile_image_url, is_enabled, is_machismo FROM seats LEFT JOIN twitter_user_cache ON seats.twitter_user_id = twitter_user_cache.user_id WHERE event_id = ? AND unregistered_at IS NULL ORDER BY registered_at';
    $sth = $self->dbh->prepare($sql);
    $sth->execute($event_id);

    $event->{machismo} = 0;
    $event->{nomachismo} = 0;
    while (my @row = $sth->fetchrow_array) {
        # X,Yが同じものは新しい値で上書き
        if ( $row[5] ) {
            # 座席情報
            $seats->[$row[0]][$row[1]] = { user_id => $row[2], screen_name => $row[3], profile_image_url => $row[4], is_enabled => 1, is_machismo => $row[6] };
            if ( defined($row[6]) ) {
                if ( $row[6] == 1 ) {
                    $event->{machismo}++;
                } else {
                    $event->{nomachismo}++;
                }
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

    # 以前座っていた席を無効化
    my $sql = 'UPDATE seats SET unregistered_at = NOW() WHERE event_id = ? AND twitter_user_id = ?';
    my $sth = $self->dbh->prepare($sql);
    $sth->execute($event_id, $user_id);

    # 座席情報を追加 (置き換えはしない)
    $sql = 'INSERT INTO seats ( event_id, seat_X, seat_Y, twitter_user_id, registered_at ) VALUE ( ?, ?, ?, ?, NOW() )';
    $sth = $self->dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y, $user_id);

    # Twitterユーザ情報キャッシュを更新
    # user_idがプライマリキーなので既存レコードがあれば更新
    $sql = 'REPLACE INTO twitter_user_cache ( user_id, screen_name, profile_image_url ) VALUE ( ?, ?, ? )';
    $sth = $self->dbh->prepare($sql);
    $sth->execute($user_id, $screen_name, $profile_image_url);
}

sub disable_seat
{
    my $self = shift;
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'INSERT INTO seats ( event_id, seat_X, seat_Y, twitter_user_id, registered_at, is_enabled ) VALUE ( ?, ?, ?, 0, NOW(), 0 )';
    my $sth = $self->dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y);
}

sub enable_seat
{
    my $self = shift;
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'UPDATE seats SET unregistered_at = NOW() WHERE event_id = ? AND seat_X = ? AND seat_Y = ? AND is_enabled = 0 AND unregistered_at IS NULL';
    my $sth = $self->dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y);
}

sub remove_seat
{
    my $self = shift;
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'UPDATE seats SET unregistered_at = NOW() WHERE event_id = ? AND seat_X = ? AND seat_Y = ? AND is_enabled = 1 AND unregistered_at IS NULL';
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


1;