import json
import mimetypes
import os.path
import subprocess

from django.conf import settings
from django.core.urlresolvers import reverse
from django.core.files.uploadedfile import UploadedFile
from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.edit import FormMixin
from django.views.generic import View
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404

from sendfile import sendfile
from sorl.thumbnail import get_thumbnail

from .models import BucketFile, Experience
from .forms import BucketUploadForm

from .api import BucketFileResource

from PIL import Image, ExifTags

class JSONResponseMixin(object):
    """
    A mixin that can be used to render a JSON response.
    """
    def render_to_json_response(self, context, **response_kwargs):
        """
        Returns a JSON response, transforming 'context' to make the payload.
        """
        return HttpResponse(
            self.convert_context_to_json(context),
            content_type='application/json',
            **response_kwargs
        )

    def convert_context_to_json(self, context):
        "Convert the context dictionary into a JSON object"
        return json.dumps(context)


class ThumbnailView(View):
    """
    A view for generating thumbnails of documents, pictures and any
    other file supported.
    FIXME: THIS VIEW IS TERRIBLE: NO CACHE AND NOTHING!
    """
    preprocess_uno = ('application/vnd.oasis.opendocument.text', 'application/msword', 'application/vnd.ms-excel', 'application/vnd.ms-powerpoint')

    def get(self, request, *args, **kwargs):
        file_id = self.kwargs['pk']
        preview_width = self.request.GET.get('width', None)
        preview_height = self.request.GET.get('height', None)
        preview_dim = self.request.GET.get('dim', None)
        border = self.request.GET.get('border', False)

        # Lookup bucket file first
        bfile = get_object_or_404(BucketFile, pk=file_id)
        # FIXME1: BUG in Tastypie causes file/image fields to be reconstructed with absolute path when PATCHing a file (see https://gist.github.com/ratpik/6308307)
        # so we strip off the /media/ if present
        if bfile.file.name[0:6] == "/media":
            bfile.file.name = bfile.file.name[7:]
        target = bfile.file.name

        # Guess mimetype
        mimetype, encoding = mimetypes.guess_type(bfile.file.url)

        # Convert document to PDF first, if needed
        # FIXME2: bug when several files are loaded => clashes
        if mimetype in ThumbnailView.preprocess_uno:
            target = '%s.pdf' % bfile.file.name
            if  os.path.isfile(os.path.join(settings.MEDIA_ROOT, target)):
                pass
            else:
                conversion_cmd = "unoconv -f pdf -o %s %s" % (os.path.join(settings.MEDIA_ROOT, target),
                                                              os.path.join(settings.MEDIA_ROOT, bfile.file.name))
                subprocess.check_output(conversion_cmd.split())

        if preview_dim:
            d = preview_dim.split('x')
            d = (int(d[0]), int(d[1]))
            try:
                image = Image.open(bfile.file.path)
            except IOError:
                image = Image.new("RGB", (int(preview_dim.split("x")[0]), int(preview_dim.split("x")[1])), "black")
            if hasattr(image, '_getexif'): # only present in JPEGs
                for orientation in ExifTags.TAGS.keys():
                    if ExifTags.TAGS[orientation]=='Orientation':
                        break
                e = image._getexif()       # returns None if no EXIF data
                if e is not None:
                    exif=dict(e.items())
                    try:
                        orientation = exif[orientation]

                        if orientation == 3:   image = image.transpose(Image.ROTATE_180)
                        elif orientation == 6: image = image.transpose(Image.ROTATE_270)
                        elif orientation == 8: image = image.transpose(Image.ROTATE_90)
                    except:
                        pass
            thumbnail_path =  os.path.join(settings.MEDIA_ROOT, os.path.splitext(os.path.basename(bfile.file.path))[0] + '_thumb_' + preview_dim + '.jpg')
            image.thumbnail(d, Image.ANTIALIAS)
            if border :
                background = Image.new('RGBA', d, (0, 0, 0, 0))
                background.paste(image,((d[0] - image.size[0]) / 2, (d[1] - image.size[1]) / 2))
                image = background
            image.save(thumbnail_path, "JPEG")
            return sendfile(request, thumbnail_path)

        try:
            thumbnail = get_thumbnail(target, preview_width or preview_height, quality=80, format='JPEG')
        except Exception:
            raise
            thumbnail = None

        if thumbnail:
            # Issue a X-Sendfile to the server
            fp = os.path.join(settings.MEDIA_ROOT, thumbnail.name)
        else:
            fp = os.path.join(settings.STATIC_ROOT, 'images/defaultfilepreview.jpg')
        return sendfile(request, fp)

class UploadView(JSONResponseMixin, FormMixin, View):
    """
    A generic HTML5 Upload view

    FIXME : deal with permissions !!
    """
    form_class = BucketUploadForm
    template_name = 'multiuploader/form.html'

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super(UploadView, self).dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.api_res = BucketFileResource()
        try:
            self.api_res.is_authenticated(request)
        except:
            raise PermissionDenied()

        form_class = self.get_form_class()

        qdict = request.POST.copy()
        qdict['uploaded_by'] = request.user.pk
        form = form_class(qdict, request.FILES)

        if form.is_valid():
            file = request.FILES.get(u'file')
            if file:
                wrapped_file = UploadedFile(file)

            # writing file manually into model
            # because we don't need form of any type.
            #
            # check if we update a file by giving an 'id' param
            if 'id' in request.POST:
                file_id = qdict['id']
                self.bf = get_object_or_404(BucketFile, pk=file_id)
                self.bf = BucketFile()
                if file:
                    self.bf.filename = wrapped_file.file.name
                    self.bf.file_size = wrapped_file.file.size
                    self.bf.file = file
                self.bf.uploaded_by = form.cleaned_data['uploaded_by'] # FIXME : security hole !!
                self.bf.bucket = form.cleaned_data['bucket']
                self.bf.title = form.cleaned_data['title']
                self.bf.type = form.cleaned_data['type']
                self.bf.url = form.cleaned_data['url']
                self.bf.video_id = form.cleaned_data['video_id']
                self.bf.video_provider = form.cleaned_data['video_provider']
                self.bf.description = form.cleaned_data['description']
                self.bf.is_author = form.cleaned_data['is_author']
                self.bf.author = form.cleaned_data['author']
                self.bf.review = form.cleaned_data['review']
                data_experience = json.loads(request.POST.get('experience_detail', '{}'))
                if data_experience:
                    exp = Experience(
                        date=data_experience['date'],
                        difficulties=data_experience['difficulties'],
                        presentation=data_experience['presentation'],
                        success=data_experience['success']
                    )
                    exp.save()
                    self.bf.experience = exp
                self.bf.save()
            # new file
            else:
                self.bf = BucketFile()
                if file:
                    self.bf.filename = wrapped_file.file.name
                    self.bf.file_size = wrapped_file.file.size
                    self.bf.file = file
                self.bf.uploaded_by = form.cleaned_data['uploaded_by'] # FIXME : security hole !!
                self.bf.bucket = form.cleaned_data['bucket']
                self.bf.title = form.cleaned_data['title']
                self.bf.type = form.cleaned_data['type']
                self.bf.url = form.cleaned_data['url']
                self.bf.video_id = form.cleaned_data['video_id']
                self.bf.video_provider = form.cleaned_data['video_provider']
                self.bf.description = form.cleaned_data['description']
                self.bf.is_author = form.cleaned_data['is_author']
                self.bf.author = form.cleaned_data['author']
                self.bf.review = form.cleaned_data['review']
                data_experience = json.loads(request.POST.get('experience_detail', '{}'))
                if data_experience:
                    exp = Experience(
                        date=data_experience['date'],
                        difficulties=data_experience['difficulties'],
                        presentation=data_experience['presentation'],
                        success=data_experience['success']
                    )
                    exp.save()
                    self.bf.experience = exp
                self.bf.save()
                if file:
                    self.bf.thumbnail_url = reverse('bucket-thumbnail', args=[self.bf.pk])
                    self.bf.save()

            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def form_invalid(self, form):
        return self.render_to_json_response({'error': 'error not implemented'})

    def form_valid(self, form):
        """
        Once saved, return the object as if we were reading the API (json, ...)
        """
        return self.api_res.get_detail(self.request, pk=self.bf.pk)
