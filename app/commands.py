from decimal import Decimal
from pathlib import Path

import click
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from .config import direct_database_url
from .extensions import db
from .models import OrderItem, Product
from .seed_data import PRODUCTS
from .services import images

SEED_IMAGES = Path(__file__).resolve().parent / "seed_images"


def _catalog_photo(filename):
    path = SEED_IMAGES / filename
    if not path.is_file():
        raise click.ClickException(f"Missing seed photo: {path.name}")
    return path.read_bytes()


def register_commands(app):
    @app.cli.command("init-db")
    def init_db():
        """Create all tables on the direct Neon connection (no migrations for this scope)."""
        direct = direct_database_url()
        if direct:
            engine = create_engine(direct, poolclass=NullPool)
            db.metadata.create_all(engine)
            engine.dispose()
        else:
            db.create_all()
        click.echo("Tables created.")

    @app.cli.command("seed")
    @click.option("--force", is_flag=True, help="Delete existing products first.")
    def seed(force):
        """Load the shop's starter catalog."""
        db.create_all()
        existing = db.session.execute(db.select(Product)).scalars().all()
        if existing and not force:
            click.echo(f"{len(existing)} products already exist; use --force to replace them.")
            return
        for product in existing:
            images.delete_urls(product.image_original_url, product.image_thumb_url)
            db.session.execute(
                db.update(OrderItem).where(OrderItem.product_id == product.id).values(product_id=None)
            )
            db.session.delete(product)
        db.session.flush()

        for item in PRODUCTS:
            original, thumb = images.process_image(_catalog_photo(item["image"]))
            original_url, thumb_url = images.store_pair(original, thumb)
            db.session.add(
                Product(
                    name=item["name"],
                    description=item["description"],
                    price=Decimal(item["price"]),
                    stock=item["stock"],
                    status="active",
                    image_original_url=original_url,
                    image_thumb_url=thumb_url,
                )
            )
        db.session.commit()
        click.echo(f"Seeded {len(PRODUCTS)} products.")
