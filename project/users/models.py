from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _

from mptt.models import MPTTModel, TreeForeignKey

from cauth.acl.models import BaseAccess
from proglangs.models import Compiler
from storage.resource_id import ResourceIdField


class UserFolder(MPTTModel):
    name = models.CharField(_('name'), max_length=64)
    parent = TreeForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children', db_index=True)
    description = models.CharField(_('description'), max_length=255, blank=True)

    def __str__(self):
        return self.name


class AdminGroup(models.Model):
    name = models.CharField(_('name'), max_length=64)
    users = models.ManyToManyField(settings.AUTH_USER_MODEL)

    def __str__(self):
        return self.name


class UserFolderAccess(BaseAccess):
    folder = models.ForeignKey(UserFolder, on_delete=models.CASCADE)
    group = models.ForeignKey(AdminGroup, on_delete=models.CASCADE, related_name='+')

    class Meta:
        unique_together = ('folder', 'group')


class UserProfile(models.Model):
    PERSON = 1
    TEAM = 2

    KIND_CHOICES = (
        (PERSON, _('Person')),
        (TEAM, _('Team')),
    )

    user = models.OneToOneField(settings.AUTH_USER_MODEL, primary_key=True, on_delete=models.CASCADE)  # required
    folder = models.ForeignKey(UserFolder, verbose_name=_('folder'), on_delete=models.PROTECT, null=True, blank=True)
    patronymic = models.CharField(_('patronymic'), max_length=30, blank=True)
    needs_change_password = models.BooleanField(_('password needs to be changed by user'), null=False, default=False)
    description = models.CharField(_('description'), max_length=255, blank=True)
    last_used_compiler = models.ForeignKey(Compiler, verbose_name=_('last used compiler'), on_delete=models.SET_NULL, null=True, blank=True)
    photo = ResourceIdField(null=True)
    photo_thumbnail = ResourceIdField(null=True)
    kind = models.IntegerField(_('kind'), choices=KIND_CHOICES, default=PERSON)
    members = models.CharField(_('members'), max_length=255, blank=True)
    can_change_name = models.BooleanField(_('user is allowed to change name'), null=False, default=False)
    can_change_password = models.BooleanField(_('user is allowed to change password'), null=False, default=True)

    def is_team(self):
        return self.kind == UserProfile.TEAM


class UserSession(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="active_session",
    )
    session_key = models.CharField(max_length=40, null=True, blank=True)

    def __str__(self):
        return f"{self.user} ({self.session_key})"


def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


post_save.connect(create_user_profile, sender=settings.AUTH_USER_MODEL)


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    if not request.session.session_key:
        request.session.save()

    UserSession.objects.update_or_create(
        user=user,
        defaults={'session_key': request.session.session_key},
    )


@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs):
    if user and user.is_authenticated:
        UserSession.objects.filter(user=user).update(session_key=None)