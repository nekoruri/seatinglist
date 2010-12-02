#!/home/masa/perl5/perlbrew/perls/perl-5.10.1/bin/perl

use utf8;
use Mojolicious::Lite;
use Net::Twitter::Lite;
use DBI;
use Data::Dumper;
use Config::Pit;

my $config = pit_get("twitter.com" , require => {
    consumer_key => 'Twitter consumer_key',
    consumer_secret => 'Twitter consumer_secret',
});

my $tw = Net::Twitter::Lite->new(
    consumer_key => $config->{consumer_key},
    consumer_secret => $config->{consumer_secret},
);

my $dbh = DBI->connect(
    $config->{db_dsn},
    $config->{db_username},
    $config->{db_password},
    { mysql_enable_utf8 => 1 }
);

# イベント一覧を表示(ID順)
get '/' => sub {
    my $self = shift;
    $self->render(events => search_all_events());
} => 'index';

# イベントの座席表を表示
get '/:event_id' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');

    my ( $event, $seats ) = generate_seats($event_id);

    $self->stash(screen_name => '');
    eval {
        # Twitterの認証が有効かを確認
        my $tw_access_token = $self->session('tw_access_token');
        my $tw_access_token_secret = $self->session('tw_access_token_secret');
        if ( $tw_access_token && $tw_access_token_secret ) {
            $tw->access_token($tw_access_token);
            $tw->access_token_secret($tw_access_token_secret);
            if ( my $user = $tw->verify_credentials ) {
                $self->stash(screen_name => $user->{screen_name});
            }
        }
    };

    $self->stash(admin => 0);
    $self->stash(event => $event);
    $self->stash(seats => $seats);
    $self->render('event');
} => 'event';

# イベントの座席表を表示
get '/:event_id/admin' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
#    $self->render(text => "event_id: $event_id\n");

    my ( $event, $seats ) = generate_seats($event_id);

    $self->stash(screen_name => '');
    eval {
        # Twitterの認証が有効かを確認
        my $tw_access_token = $self->session('tw_access_token');
        my $tw_access_token_secret = $self->session('tw_access_token_secret');
        if ( $tw_access_token && $tw_access_token_secret ) {
            $tw->access_token($tw_access_token);
            $tw->access_token_secret($tw_access_token_secret);
            if ( my $user = $tw->verify_credentials ) {
                $self->stash(screen_name => $user->{screen_name});
            }
        }
    };

    $self->stash(admin => 1);
    $self->stash(event => $event);
    $self->stash(seats => $seats);
    $self->render('event');
} => 'event_admin';

# 座席表に席を登録
get '/:event_id/seat/:x/:y' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
    my $seat_X = $self->param('x');
    my $seat_Y = $self->param('y');

    # Twitterの認証が有効かを確認
    my $tw_access_token = $self->session('tw_access_token');
    my $tw_access_token_secret = $self->session('tw_access_token_secret');

    if ( $tw_access_token && $tw_access_token_secret ) {
        $tw->access_token($tw_access_token);
        $tw->access_token_secret($tw_access_token_secret);

        update_seat($event_id, $seat_X, $seat_Y);
        $self->redirect_to($self->url_for('event')->to_abs."$event_id");
        return;
    }

    # 無効ならば、request_tokenをもらってauthorization開始
#    my $callback_url = $self->url_for('index')->to_abs . "$event_id/seat/$seat_X/$seat_Y/authorized";
    my $callback_url = "http://seats.nekoruri.jp/$event_id/seat/$seat_X/$seat_Y/authorized";
    my $auth_url = $tw->get_authorization_url(callback => $callback_url);

    $self->session('tw_request_token' => $tw->request_token);
    $self->session('tw_request_token_secret' => $tw->request_token_secret);

    $self->redirect_to($auth_url);
};

post '/:event_id/seat/:x/:y' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
    my $seat_X = $self->param('x');
    my $seat_Y = $self->param('y');

    if ($self->param('remove')) {
        remove_seat($event_id, $seat_X, $seat_Y);
    } elsif ($self->param('machismo')) {
        machismo_seat($event_id, $seat_X, $seat_Y);
    } elsif ($self->param('nomachismo')) {
        nomachismo_seat($event_id, $seat_X, $seat_Y);
    }
    $self->redirect_to($self->url_for('event')->to_abs."$event_id");
};

get '/:event_id/seat/:x/:y/authorized' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
    my $seat_X = $self->param('x');
    my $seat_Y = $self->param('y');

    my $verifier = $self->param('oauth_verifier');
    if ($verifier) {
        $tw->request_token( $self->session('tw_request_token') );
        $tw->request_token_secret( $self->session('tw_request_token_secret' ) );

        eval { 
            my ($access_token, $access_token_secret, $user_id, $screen_name) = $tw->request_access_token(verifier => $verifier);

            $self->session(tw_access_token => $access_token);
            $self->session(tw_access_token_secret => $access_token_secret);
        }; if ($@) {
            warn Dumper($@);
        }
        update_seat($event_id, $seat_X, $seat_Y);
        $self->redirect_to($self->url_for('event')->to_abs."$event_id");
    }
#    $self->redirect_to('event');
};


get '/:event_id/seat/:x/:y/disable' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
    my $seat_X = $self->param('x');
    my $seat_Y = $self->param('y');

    disable_seat($event_id, $seat_X, $seat_Y);
    $self->redirect_to($self->url_for('event')->to_abs."$event_id/admin");
};

get '/:event_id/seat/:x/:y/enable' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
    my $seat_X = $self->param('x');
    my $seat_Y = $self->param('y');

    enable_seat($event_id, $seat_X, $seat_Y);
    $self->redirect_to($self->url_for('event')->to_abs."$event_id/admin");
};

app->types->type(html => 'text/html; charset=utf-8');
app->start;

sub generate_seats
{
    my ( $event_id ) = @_;

    my $sql = 'SELECT title, seats_X, seats_Y FROM events WHERE id = ?';
    my $sth = $dbh->prepare($sql);
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
    $sth = $dbh->prepare($sql);
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
#warn Dumper($seats);
    return ($event, $seats);
}

sub update_seat
{
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    if ( my $user = $tw->verify_credentials ) {
        # 有効ならば、そのまま席を登録
        my $user_id = $user->{id};
        my $screen_name = $user->{screen_name};
        my $profile_image_url = $user->{profile_image_url};

        # 以前座っていた席を無効化
        my $sql = 'UPDATE seats SET unregistered_at = NOW() WHERE event_id = ? AND twitter_user_id = ?';
        my $sth = $dbh->prepare($sql);
        $sth->execute($event_id, $user_id);

        # 座席情報を追加 (置き換えはしない)
        $sql = 'INSERT INTO seats ( event_id, seat_X, seat_Y, twitter_user_id, registered_at ) VALUE ( ?, ?, ?, ?, NOW() )';
        $sth = $dbh->prepare($sql);
        $sth->execute($event_id, $seat_X, $seat_Y, $user_id);

        # Twitterユーザ情報キャッシュを更新
        # user_idがプライマリキーなので既存レコードがあれば更新
        $sql = 'REPLACE INTO twitter_user_cache ( user_id, screen_name, profile_image_url ) VALUE ( ?, ?, ? )';
        $sth = $dbh->prepare($sql);
        $sth->execute($user_id, $screen_name, $profile_image_url);

        return;
    }

}

sub disable_seat
{
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'INSERT INTO seats ( event_id, seat_X, seat_Y, twitter_user_id, registered_at, is_enabled ) VALUE ( ?, ?, ?, 0, NOW(), 0 )';
    my $sth = $dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y);
}

sub enable_seat
{
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'UPDATE seats SET unregistered_at = NOW() WHERE event_id = ? AND seat_X = ? AND seat_Y = ? AND is_enabled = 0 AND unregistered_at IS NULL';
    my $sth = $dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y);
}

sub remove_seat
{
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'UPDATE seats SET unregistered_at = NOW() WHERE event_id = ? AND seat_X = ? AND seat_Y = ? AND is_enabled = 1 AND unregistered_at IS NULL';
    my $sth = $dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y);
}

sub machismo_seat
{
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'UPDATE seats SET is_machismo = 1 WHERE event_id = ? AND seat_X = ? AND seat_Y = ? AND is_enabled = 1 AND unregistered_at IS NULL';
    my $sth = $dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y);
}

sub nomachismo_seat
{
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'UPDATE seats SET is_machismo = 0 WHERE event_id = ? AND seat_X = ? AND seat_Y = ? AND is_enabled = 1 AND unregistered_at IS NULL';
    my $sth = $dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y);
}

# DB系ファサード

# 全てのイベントをID順に表示
sub search_all_events
{
    my $sql = 'SELECT id, title FROM events ORDER BY id';
    my $sth = $dbh->prepare($sql);
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

__DATA__

@@ index.html.ep
<html>
<head>
    <title>イベント座席表</title>
    <script type="text/javascript">
      var _gaq = _gaq || [];
      _gaq.push(['_setAccount', 'UA-19946424-1']);
      _gaq.push(['_trackPageview']);

      (function() {
        var ga = document.createElement('script'); ga.type = 'text/javascript'; ga.async = true;
        ga.src = ('https:' == document.location.protocol ? 'https://ssl' : 'http://www') + '.google-analytics.com/ga.js';
        var s = document.getElementsByTagName('script')[0]; s.parentNode.insertBefore(ga, s);
      })();
    </script>
</head>
<body>

<h1>イベント一覧</h1>
<p>現状では#qpstudy04のみです。</p>
<ul>
<% foreach my $event ( @$events ) { %>
    <li><a href="/<%= $event->{id} %>"><%= $event->{title} %></a></li>
<% } %>
</ul>

<address>
<p>作った人: Aki<a href="http://twitter.com/nekoruri/">@nekoruri</a></p>
</address>

</body>
</html>
@@ event.html.ep
<html>
<head>
    <title>座席表 [ <%= $event->{title} %> ]</title>
    <script type="text/javascript" src="http://ajax.googleapis.com/ajax/libs/jquery/1.4.2/jquery.min.js"></script>
    <script type="text/javascript">
      var _gaq = _gaq || [];
      _gaq.push(['_setAccount', 'UA-19946424-1']);
      _gaq.push(['_trackPageview']);

      (function() {
        var ga = document.createElement('script'); ga.type = 'text/javascript'; ga.async = true;
        ga.src = ('https:' == document.location.protocol ? 'https://ssl' : 'http://www') + '.google-analytics.com/ga.js';
        var s = document.getElementsByTagName('script')[0]; s.parentNode.insertBefore(ga, s);
      })();

    </script>
</head>
<link rel="stylesheet" href="/style.css" type="text/css">
<body>

<div class="ad">
<script type="text/javascript"><!--
google_ad_client = "ca-pub-4628387712169493";
/* イベントページ トップバナー */
google_ad_slot = "8384267503";
google_ad_width = 728;
google_ad_height = 90;
//-->
</script>
<script type="text/javascript"
src="http://pagead2.googlesyndication.com/pagead/show_ads.js">
</script>
</div>

<h1>座席表 [ <%= $event->{title} %> ]</h1>
<table border="1">
    <thead>
    <tr><th colspan="<%= $event->{seats_X}+1 %>">前</th></tr>
    <tr><th>Y ＼ X</th>
<%      foreach my $x ( 0 ... $event->{seats_X}-1 ) { %>
        <th><%= $x %></td>
<%      } %>
    </tr></thead><tfoot></tfoot><tbody>
<% foreach my $y ( 0 ... $event->{seats_Y}-1 ) { %>
    <tr><th><%= $y %></th>
<%      foreach my $x ( 0 ... $event->{seats_X}-1 ) { %>
<%          if ( my $seat = $seats->[$x][$y] ) { %>
<%              if ( $seat->{is_enabled} ) { %>
<%                  if ( $seat->{screen_name} eq $screen_name ) { %>
        <form method="POST" action="/<%= $event_id %>/seat/<%= $x %>/<%= $y %>">
        <td class="myself"><a href="http://twitter.com/<%= $seat->{screen_name} %>"><%= $seat->{screen_name} %></a><br />
            <img src="<%= $seat->{profile_image_url} %>" /><br />
            <span style="font-size: xx-small">
            <input type="submit" name="remove" value="消す" /><br />
<%                      if ( defined($seat->{is_machismo}) ) { %>
                [ <%= $seat->{is_machismo} == 1 ? 'マッチョ' : 'ウィンプ' %> ]
<%                      } else { %>
            <input type="submit" name="machismo" value="マッチョ" />
            <input type="submit" name="nomachismo" value="ウィンプ" /><br />
<%                      } %></span>
        </td>
        </form>
<%                  } else { %>
        <form method="POST" action="/<%= $event_id %>/seat/<%= $x %>/<%= $y %>">
        <td><a href="http://twitter.com/<%= $seat->{screen_name} %>"><%= $seat->{screen_name} %></a><br />
            <img src="<%= $seat->{profile_image_url} %>" /><br />
            <span style="font-size: xx-small">
            <input type="submit" name="remove" value="消す" /><br />
<%                      if ( defined($seat->{is_machismo}) ) { %>
                [ <%= $seat->{is_machismo} == 1 ? 'マッチョ' : 'ウィンプ' %> ]
<%                      } else { %>
            <input type="submit" name="machismo" value="マッチョ" />
            <input type="submit" name="nomachismo" value="ウィンプ" /><br />
<%                      } %></span>
        </td>
        </form>
<%                  } %>
<%              } else { %>
<%                  if ( $admin ) { %>
        <td class="disabled"><a href="/<%= $event_id %>/seat/<%= $x %>/<%= $y %>/enable">戻す</a></td>
<%                  } else { %>
        <td class="disabled">-</td>
<%                  } %>
<%              } %>
<%          } else { %>
<%              if ( $admin ) { %>
        <td><a href="/<%= $event_id %>/seat/<%= $x %>/<%= $y %>/disable">予約</a></td>
<%              } else { %>
        <td><a href="/<%= $event_id %>/seat/<%= $x %>/<%= $y %>">ｲﾏｺｺ</a></td>
<%              } %>
<%          } %>
<%      } %>
    </tr>
<% } %>
</tbody></table>

<hr />
<p>備考:</p>
<ul>
<li><a href="http://twitter.com/synboo/">@synboo</a>さんの作成された<a href="http://synboo.com/twitterconf2/">twitterconf2の座席表システム</a><del>をパクった</del>にインスパイアされて作った座席表システムです。</li>
<li>ｲﾏｺｺを押すと、Twitterの認証画面経由で座席表のその席を登録できます。</li>
<li>最後に登録した一箇所のみが有効です。座席を間違えたら、正しい位置で登録すれば移動します。</li>
<li>TwitterのアクセストークンはブラウザのCookieに保存されているのでシステム側には保存しません。</li>
<li>他の人が席を独り占めしっぱなしの時は、その人を消してから乗っ取ってください。</li>
<li>マッチョ: <%= $event->{machismo} %>人 / ウィンプ: <%= $event->{nomachismo} %>人</li>
</ul>
</p>

<address>
<p>作った人: Aki<a href="http://twitter.com/nekoruri/">@nekoruri</a></p>
</address>

</body>
</html>

