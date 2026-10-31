from import_export import resources, fields
from .models import Product



class ProductResource(resources.ModelResource):

    class Meta:
        model = Product

