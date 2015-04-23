from django.db import models
from django.db.models.signals import post_save, pre_save
from django.contrib.auth.models import User
from django.utils.translation import ugettext as _

from projects.models import Project
from autoslug.fields import AutoSlugField
from bucket.models import Bucket, BucketFile
from jsonfield import JSONField

class ProjectSheetTemplate(models.Model):
    name = models.CharField(max_length=100)
    slug = AutoSlugField(unique=True, populate_from="name", always_update=True)
    shortdesc = models.CharField(max_length=255, null=True, blank=True)

    def __unicode__(self):
        return self.name

class ProjectSheetQuestion(models.Model):
    template = models.ForeignKey(ProjectSheetTemplate, related_name='questions')
    order = models.PositiveIntegerField(default=0)
    text = models.CharField(max_length=255)

    def __unicode__(self):
        return u"%s - %s" % (self.order, self.text)

    class Meta:
        ordering = ('order',)

class QuestionChoice(models.Model):
    question = models.ForeignKey(ProjectSheetQuestion, related_name='choices')
    text = models.CharField(max_length=255)
    value = models.PositiveIntegerField(default=0)
    
    def save(self, *args, **kwargs):
        if self.question.choices.all().count() == 0:
            self.value = 1
        else:
            max_val = 0
            for choice in self.question.choices.all():
                if choice.value > max_val:
                    max_val = choice.value
            self.value = max_val + 1
            
        super(QuestionChoice, self).save(*args, **kwargs)

class ProjectSheet(models.Model):
    project = models.OneToOneField(Project)
    template = models.ForeignKey(ProjectSheetTemplate)
    bucket = models.ForeignKey(Bucket, null=True, blank=True)
    cover = models.ForeignKey(BucketFile, null=True, blank=True)
    videos = JSONField(default=None, blank=True, null=True)

    def __unicode__(self):
        return u"%s %s" % (_('Project sheet for '), self.project)

def createProjectSheetBucket(sender, instance, **kwargs):
    bucket_name = instance.project.slug
    bucket_owner = User.objects.get(pk=-1) # FIXME : to whom should bucket projects belong ? default to Anonymous user by now
    projectsheet_bucket, created = Bucket.objects.get_or_create(created_by=bucket_owner,
                                                name=bucket_name)
    instance.bucket = projectsheet_bucket

class ProjectSheetQuestionAnswer(models.Model):
    """
    Answer to a question for a given project
    """
    class Meta:
        ordering = ("question__order",)

    projectsheet = models.ForeignKey(ProjectSheet, related_name='question_answers')
    question = models.ForeignKey(ProjectSheetQuestion, related_name='answers')
    answer = models.TextField(blank=True)
    selected_choices = models.CommaSeparatedIntegerField(max_length=255, null=True, blank=True)

    def __unicode__(self):
        return u"Answer to question <%s> for <%s>" % (self.question, self.projectsheet)

pre_save.connect(createProjectSheetBucket, ProjectSheet)
