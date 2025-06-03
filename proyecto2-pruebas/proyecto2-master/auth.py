class Authorization:
    def __init__(self, user, ticket, CSRFPreventionToken):
        self.user = user
        self.ticket = ticket
        self.CSRFPreventionToken = CSRFPreventionToken

    def is_valid(self):
        return bool(self.ticket and self.CSRFPreventionToken)

    def get_headers(self):
        return {
            "Cookie": f"PVEAuthCookie={self.ticket}",
            "CSRFPreventionToken": self.CSRFPreventionToken,
            "Content-Type": "application/x-www-form-urlencoded"
        }

    def refresh_tokens(self, new_ticket, new_csrf_token):
        self.ticket = new_ticket
        self.CSRFPreventionToken = new_csrf_token
