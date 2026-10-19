pragma Singleton

import QtQuick

/*!
    The palette and metrics.

    The look is flat and dense: one-pixel borders instead of shadows, square
    corners, small monospace capitals for labels and a single saturated blue
    that is only ever used to say "this is the active thing".
*/
QtObject {
    id: theme

    // --- surfaces ---------------------------------------------------------
    readonly property color bg: "#0c0d11"
    readonly property color panel: "#0e0f13"
    readonly property color bar: "#101116"
    readonly property color border: "#1c1e25"
    readonly property color borderStrong: "#2a2d37"
    readonly property color rowHover: "#13151a"
    readonly property color rowSelected: "#171a21"

    // --- text -------------------------------------------------------------
    readonly property color text: "#f1f2f5"
    readonly property color muted: "#9096a3"
    readonly property color faint: "#5a5f6e"
    readonly property color darkOnLight: "#0c0d11"   // text on the white "active" fill
    readonly property color light: "#f1f2f5"

    // --- accents ----------------------------------------------------------
    readonly property color accent: "#2f63e6"
    readonly property color accentText: "#6b93ff"
    readonly property color positive: "#3dd68c"
    readonly property color warning: "#f0a93a"
    readonly property color negative: "#ef5b6f"

    // --- fonts ------------------------------------------------------------
    // QML has no font fallback list, so pick the first installed family here.
    function firstInstalled(candidates, fallback) {
        const installed = Qt.fontFamilies()
        for (let i = 0; i < candidates.length; ++i) {
            if (installed.indexOf(candidates[i]) >= 0)
                return candidates[i]
        }
        return fallback
    }
    readonly property string monoFamily: firstInstalled(
        ["Cascadia Mono", "Cascadia Code", "Consolas", "Lucida Console", "Courier New"], "monospace")
    // Phones have no Segoe icons, so they use the bundled Material Icons instead.
    readonly property bool mobileIcons: Qt.platform.os === "android" || Qt.platform.os === "ios"
    readonly property string iconFamily: mobileIcons ? "Material Icons" : firstInstalled(
        ["Segoe Fluent Icons", "Segoe MDL2 Assets"], "Segoe UI Symbol")
    readonly property string sans: "Segoe UI"

    // --- metrics ----------------------------------------------------------
    readonly property int barHeight: 40
    readonly property int headerHeight: 36
    readonly property int rowHeight: 34
    readonly property int transportHeight: 56
    readonly property int sidebarWidth: 232
    readonly property int detailWidth: 330

    readonly property int fontLabel: 11
    readonly property int fontSmall: 12
    readonly property int fontBody: 13
    readonly property int fontTitle: 20

    // --- icon glyphs (Segoe Fluent Icons / Segoe MDL2 Assets) ---------------
    readonly property string iPlay: mobileIcons ? "\ue037" : ""
    readonly property string iPause: mobileIcons ? "\ue034" : ""
    readonly property string iPrev: mobileIcons ? "\ue045" : ""
    readonly property string iDelete: mobileIcons ? "\ue872" : ""
    readonly property string iFolder: mobileIcons ? "\ue2c8" : ""
    readonly property string iSettings: mobileIcons ? "\ue8b8" : ""
    readonly property string iEdit: mobileIcons ? "\ue3c9" : ""
    readonly property string iNext: mobileIcons ? "\ue044" : ""
    readonly property string iHeart: mobileIcons ? "\ue87e" : ""
    readonly property string iHeartFill: mobileIcons ? "\ue87d" : ""
    readonly property string iDislike: mobileIcons ? "\ue9f2" : ""
    readonly property string iVolume: mobileIcons ? "\ue050" : ""
    readonly property string iMute: mobileIcons ? "\ue04f" : ""
    readonly property string iSearch: mobileIcons ? "\ue8b6" : ""
    readonly property string iRefresh: mobileIcons ? "\ue5d5" : ""
    readonly property string iAdd: mobileIcons ? "\ue145" : ""
    readonly property string iClose: mobileIcons ? "\ue5cd" : ""
    readonly property string iChevronDown: mobileIcons ? "\ue5cf" : ""
    readonly property string iChevronUp: mobileIcons ? "\ue5ce" : ""
    readonly property string iPanel: mobileIcons ? "\uf114" : ""
    readonly property string iLogout: mobileIcons ? "\ue9ba" : ""
    readonly property string iWave: mobileIcons ? "\ue1b8" : ""
    readonly property string iLibrary: mobileIcons ? "\ue030" : ""
    readonly property string iCatalogue: mobileIcons ? "\ue574" : ""
    readonly property string iTune: mobileIcons ? "\ue429" : "\ue71c"
    readonly property string iBlock: mobileIcons ? "\ue14b" : ""
    readonly property string iMinimize: mobileIcons ? "\ue931" : ""
    readonly property string iMaximize: mobileIcons ? "\ue3c6" : ""
    readonly property string iRestore: mobileIcons ? "\ue3e0" : ""
    readonly property string iWinClose: mobileIcons ? "\ue5cd" : ""

    function alpha(baseColor, amount) {
        return Qt.rgba(baseColor.r, baseColor.g, baseColor.b, amount)
    }
}
