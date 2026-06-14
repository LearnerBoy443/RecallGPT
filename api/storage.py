from django.core.files.storage import Storage
from django.core.files.base import ContentFile

class DatabaseStorage(Storage):
    def _open(self, name, mode='rb'):
        from .models import DatabaseFile
        try:
            db_file = DatabaseFile.objects.get(name=name)
            return ContentFile(db_file.content, name=name)
        except DatabaseFile.DoesNotExist:
            raise FileNotFoundError(f"File not found: {name}")

    def _save(self, name, content):
        from .models import DatabaseFile
        # Ensure name uses forward slashes for URL and path consistency
        name = name.replace('\\', '/')
        content_bytes = content.read()
        db_file, created = DatabaseFile.objects.update_or_create(
            name=name,
            defaults={
                'content': content_bytes,
                'size': len(content_bytes)
            }
        )
        return name

    def exists(self, name):
        from .models import DatabaseFile
        name = name.replace('\\', '/')
        return DatabaseFile.objects.filter(name=name).exists()

    def delete(self, name):
        from .models import DatabaseFile
        name = name.replace('\\', '/')
        DatabaseFile.objects.filter(name=name).delete()

    def size(self, name):
        from .models import DatabaseFile
        name = name.replace('\\', '/')
        try:
            return DatabaseFile.objects.get(name=name).size
        except DatabaseFile.DoesNotExist:
            return 0

    def url(self, name):
        name = name.replace('\\', '/')
        return f"/api/media/serve/{name}"
