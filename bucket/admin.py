from django.contrib import admin

from .models import Bucket, BucketFile

class InlineBucketFile(admin.TabularInline):
    model = BucketFile

class BucketAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by')
    search_fields = ('name', )
    inlines = [
        InlineBucketFile,
    ]

admin.site.register(Bucket, BucketAdmin)
