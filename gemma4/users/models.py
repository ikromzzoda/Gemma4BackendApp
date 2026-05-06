from fireo import models

class User(models.Model):
    first_name = models.TextField(required=True)
    last_name = models.TextField(required=True)
    username = models.TextField(required=True)
    email = models.TextField(required=True)
    password = models.TextField(required=True)  
    date_of_birth = models.DateTime(required=True)
    location = models.TextField(required=False)

    class Meta:
        collection_name = "users"