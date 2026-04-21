from fireo import models

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gemma4.settings')
django.setup()


class User(models.Model):
    first_name = models.TextField(max_length=200, blank=False)
    last_name = models.TextField(max_length=200, blank=False)
    username = models.TextField(max_length=100, unique=True, blank=False)
    email = models.models.EmailField(("Email"), max_length=254)
    password = models.set_password(models.TextField())
    date_of_birth = models.DateTime(blank=False, null=False)  

    class Meta:
        collection_name = "users"

