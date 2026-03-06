"""Facebook Account Manager — backward-compatible wrapper around SocialAccountManager"""
from shared.social_account_manager import social_account_manager


class FBAccountManagerCompat:
    """Thin wrapper that delegates to SocialAccountManager with platform='facebook'."""

    def init(self):
        social_account_manager.init()

    def get_account(self):
        return social_account_manager.get_account("facebook")

    def get_all_accounts(self):
        return social_account_manager.get_all_accounts("facebook")

    def get_account_by_id(self, account_id):
        return social_account_manager.get_account_by_id(account_id)

    def mark_used(self, account_id):
        social_account_manager.mark_used(account_id)

    def mark_failed(self, account_id):
        social_account_manager.mark_failed(account_id)

    def mark_success(self, account_id):
        social_account_manager.mark_success(account_id)

    def save_cookies(self, account_id, cookies):
        social_account_manager.save_cookies(account_id, cookies)

    def get_cookies(self, account_id):
        return social_account_manager.get_cookies(account_id)

    def add_account(self, email, password, notes=None):
        return social_account_manager.add_account("facebook", email, password, notes)

    def delete_account(self, account_id):
        return social_account_manager.delete_account(account_id)

    def update_status(self, account_id, status):
        return social_account_manager.update_status(account_id, status)

    def get_stats(self):
        return social_account_manager.get_stats("facebook")

    def login_facebook(self, driver, account):
        return social_account_manager.login(driver, account)

    def ensure_logged_in(self, driver):
        return social_account_manager.ensure_logged_in(driver, "facebook")


fb_account_manager = FBAccountManagerCompat()
