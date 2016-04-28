""" Projects and related models. """

from django.db import models
# from django.contrib.auth.models import Group
from simple_history.models import HistoricalRecords

from autoslug.fields import AutoSlugField
from taggit.managers import TaggableManager
from scout.models import Place
from accounts.models import Profile


class ProjectProgressRange(models.Model):

    """ A project progress range. """

    name = models.CharField(max_length=100)
    slug = AutoSlugField(unique=True, populate_from="name", always_update=True)

    def __unicode__(self):
        """ pep257, you know I love you. """

        return u"%s" % self.name


class ProjectProgress(models.Model):

    """ A project progress. """

    progress_range = models.ForeignKey(ProjectProgressRange)
    order = models.PositiveIntegerField(default=0)
    label = models.CharField(max_length=30)
    description = models.CharField(max_length=500)
    icon = models.ImageField(upload_to='progress_icons', null=True, blank=True)

    class Meta:
        ordering  = ['order', ]

    def __unicode__(self):
        """ pep257, you know I love you. """

        return u"%s - %s - %s" % (self.progress_range, self.order, self.label)


class Project(models.Model):

    """ A project is any idea you can document. """

    title = models.CharField(max_length=100)
    slug = AutoSlugField(unique=True,
                         populate_from='title',
                         unique_with=['title'])
    baseline = models.CharField(max_length=250, null=True, blank=True)
    tags = TaggableManager(blank=True)
    description = models.TextField(blank=True)
    location = models.ForeignKey(Place, null=True, blank=True, on_delete=models.SET_NULL)
    website = models.URLField(null=True, blank=True)
    begin_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    progress = models.ForeignKey(ProjectProgress, null=True, blank=True, on_delete=models.SET_NULL)
    created_on = models.DateTimeField(auto_now_add=True)

    # groups = models.ManyToManyField(Group, null=True, blank=True)

    history = HistoricalRecords()

    def __unicode__(self):
        """ pep257, you know I love you. """
        return self.title

class ProjectNews(models.Model):
    """ Basic news about a projet """

    title = models.CharField(max_length=100)
    text = models.TextField(blank=True)
    author = models.ForeignKey(Profile)
    project = models.ForeignKey(Project)
    timestamp = models.DateTimeField(auto_now_add=True)

# XXX/TODO: obsolete
class ProjectTeam(models.Model):

    """ A project team.

    .. todo:: this model is probably obsolete.
        Someones knowing the truth checks it?
        Does the project group replaces it ?
    """

    project = models.ForeignKey(Project)
    members = models.ManyToManyField(Profile)
