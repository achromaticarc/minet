# =============================================================================
# Minet Instagram User-followings CLI Action
# =============================================================================
#
# Logic of the `instagram user-followings` action.
#
from itertools import islice

from minet.cli.utils import with_enricher_and_loading_bar
from minet.cli.instagram.utils import with_instagram_fatal_errors
from minet.instagram import InstagramAPIScraper
from minet.instagram.constants import INSTAGRAM_USER_CSV_HEADERS
from minet.instagram.exceptions import (
    InstagramInvalidTargetError,
    InstagramPrivateAccountError,
    InstagramAccountNoFollowError,
)


@with_instagram_fatal_errors
@with_enricher_and_loading_bar(
    headers=INSTAGRAM_USER_CSV_HEADERS,
    title="Scraping followees",
    unit="users",
    nested=True,
    sub_unit="followees",
)
def action(cli_args, enricher, loading_bar):
    client = InstagramAPIScraper(cookie=cli_args.cookie)

    for i, (row, user) in enumerate(enricher.cells(cli_args.column, with_rows=True)):
        with loading_bar.tick(user):
            try:
                generator = client.user_following(user)

                if cli_args.limit:
                    generator = islice(generator, cli_args.limit)

                for post in generator:
                    enricher.writerow(row, post.as_csv_row())
                    loading_bar.nested_advance()

            except InstagramInvalidTargetError:
                loading_bar.print(
                    "Given user (line %i) is probably not an Instagram user: %s"
                    % (i, user)
                )

            except InstagramAccountNoFollowError:
                loading_bar.print(
                    "Given user (line %i) probably doesn't follow any account: %s"
                    % (i, user)
                )

            except InstagramPrivateAccountError as nb_follow:
                loading_bar.print(
                    "Given user (line %i) is probably a private account following %s accounts: %s"
                    % (i, nb_follow, user)
                )
