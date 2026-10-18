import QtQuick

/*!
    A glyph from the system icon font.

    The font ships with Windows 10 and 11, so there are no image assets to
    package or scale. Linux and Android builds will need an icon font bundled
    with the app instead; only the glyph table in Theme.qml has to change.
*/
Text {
    property string glyph: ""

    text: glyph
    color: Theme.muted
    font.family: Theme.iconFamily
    font.pixelSize: 14
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
}
