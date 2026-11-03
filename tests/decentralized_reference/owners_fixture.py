from app.database.conversation_owners import ConversationNotFound
class TestOwners:
    __test__ = False
    def __init__(self): self.rows = {}
    def register(self, *, conversation_id, thread_id, authenticated_customer_id):
        row = dict(thread_id=thread_id, customer_id=authenticated_customer_id)
        self.rows[conversation_id] = row
        return row
    def authorize(self, *, conversation_id, authenticated_customer_id):
        row = self.rows.get(conversation_id)
        if row is None or row["customer_id"] != authenticated_customer_id: raise ConversationNotFound()
        return row
