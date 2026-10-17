pragma Singleton

import QtQuick

/*!
    The whole palette in one place.

    Wavelane is a dark player by default: album art is the brightest thing on
    screen, so the chrome around it stays low-contrast and out of the way.
*/
QtObject {
    id: theme

    // --- surfaces ---------------------------------------------------------
    readonly property color background: "#0C0D12"
    readonly property color surface: "#15171F"
    readonly property color surfaceHover: "#1D2029"
    readonly property color surfaceActive: "#262A36"
    readonly property color border: "#262A36"

    // --- text -------------------------------------------------------------
    readonly property color text: "#F2F3F7"
    readonly property color textMuted: "#9AA0B0"
    readonly property color textFaint: "#636a7d"

    // --- brand ------------------------------------------------------------
    // The wave gradient: Wavelane's one piece of strong colour.
    readonly property color accent: "#5B8CFF"
    readonly property color accentAlt: "#9A6BFF"
    readonly property color accentSoft: "#2A3350"
    readonly property color positive: "#3DD68C"
    readonly property color negative: "#F4617A"
    readonly property color warning: "#F5A524"

    // --- metrics ----------------------------------------------------------
    readonly property int radiusSmall: 6
    readonly property int radius: 12
    readonly property int radiusLarge: 20
    readonly property int spacing: 12
    readonly property int spacingLarge: 20
    readonly property int sidebarWidth: 220
    readonly property int playerBarHeight: 88

    readonly property int fontTiny: 11
    readonly property int fontSmall: 13
    readonly property int fontBody: 14
    readonly property int fontTitle: 18
    readonly property int fontHeading: 26
    readonly property int fontDisplay: 34

    readonly property int durationFast: 120
    readonly property int durationNormal: 220

    function alpha(baseColor, amount) {
        return Qt.rgba(baseColor.r, baseColor.g, baseColor.b, amount)
    }
}
