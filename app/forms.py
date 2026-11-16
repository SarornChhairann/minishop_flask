from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import DecimalField, IntegerField, PasswordField, SelectField, StringField, TextAreaField
from wtforms.fields.choices import SelectChoice
from wtforms.validators import DataRequired, Length, NumberRange, Regexp


class CheckoutForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    email = StringField(
        "Email address",
        validators=[
            DataRequired(),
            Length(max=254),
            Regexp(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", message="Enter a valid email address."),
        ],
    )
    phone = StringField(
        "Phone number",
        validators=[
            DataRequired(),
            Regexp(r"^\+?[0-9 ()-]{6,20}$", message="Enter a valid phone number."),
        ],
    )
    address = TextAreaField("Shipping address", validators=[DataRequired(), Length(max=500)])


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])


class ProductForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    description = TextAreaField("Description", validators=[DataRequired(), Length(max=4000)])
    price = DecimalField(
        "Price (USD)", places=2, validators=[DataRequired(), NumberRange(min=0.01, max=99999999)]
    )
    stock = IntegerField("Stock quantity", validators=[NumberRange(min=0, max=1_000_000)])
    image = FileField(
        "Image", validators=[FileAllowed(["jpg", "jpeg", "png", "webp"], "Use a JPEG, PNG or WEBP image.")]
    )
    status = SelectField("Status", choices=[SelectChoice("active", "Active"), SelectChoice("inactive", "Inactive")])
