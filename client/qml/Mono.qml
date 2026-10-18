import QtQuick

/*! The small monospace capitals used for every label and number. */
Text {
    color: Theme.muted
    font.family: Theme.monoFamily
    font.pixelSize: Theme.fontLabel
    font.letterSpacing: 0.8
    font.capitalization: Font.AllUppercase
    elide: Text.ElideRight
    verticalAlignment: Text.AlignVCenter
}
