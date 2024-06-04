class ESkatRouter:
    # Makes all non managed models in the eskat app use the actual eskat database.
    # Disallows migrations for the eskat database.

    def db_for_read(self, model, **hints):
        # All eskat tables should use the eskat database
        if model._meta.app_label and not model._meta.managed:
            return "eskat"
        return None

    def db_for_write(self, model, **hints):
        # All eskat tables should use the eskat database
        if model._meta.app_label and not model._meta.managed:
            return "eskat"
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Return None so the default where objects have to be from
        # the same database is used.
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # Allow no migrations for eskat database
        if db == "eskat":
            return False
        return None
