from fireo import models


class User(models.Model):
    uid = models.TextField(required=True)
    firstName = models.TextField(required=True)
    surname = models.TextField(required=True)
    email = models.TextField(required=True)
    location = models.TextField(required=False, default="Dushanbe")
    ageGroup = models.TextField(required=False, default="18 - 24")
    healthCondition = models.TextField(required=False, default="None")
    activityLevel = models.TextField(required=False, default="Active")
    notificationsEnabled = models.BooleanField(required=False, default=True)
    dailyForecastEnabled = models.BooleanField(required=False, default=True)
    healthTipsEnabled = models.BooleanField(required=False, default=False)
    profilePicUrl = models.TextField(required=False)
    fcmToken = models.TextField(required=False, default="")

    class Meta:
        collection_name = "users"
