from django import forms
from .models import Current_emscall, Current_ambulance


class CurrentCallForm(forms.ModelForm):
    """Form to input address of current emergency call."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['addr'].required = False
        self.fields['addr'].label = "Address"
        self.fields['addr'].widget.attrs.update({
            'class': 'form-ctrl',
            'placeholder': 'e.g. Sector 22 Market, Chandigarh',
            'autocomplete': 'off',
        })

    class Meta:
        model = Current_emscall
        fields = ("addr",)


def get_ambulance_choices():
    """Return list of (amb_id, label) for all ambulances."""
    ambs = Current_ambulance.objects.all().order_by('amb_id')
    choices = []
    for a in ambs:
        status = "Active" if a.AVAILABLE else "Inactive"
        choices.append((a.amb_id, f"#{a.amb_id} — {status}"))
    return choices


class CurrentAmbulanceForm(forms.Form):
    """Form to select an ambulance to reactivate."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['amb_id'] = forms.ChoiceField(
            choices=get_ambulance_choices(),
            label="Ambulance ID",
            required=False,
            widget=forms.Select(attrs={'class': 'form-ctrl'})
        )
