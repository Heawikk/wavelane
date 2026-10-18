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
    readonly property string iconFamily: firstInstalled(
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
    readonly property string iPlay: ""
    readonly property string iPause: ""
    readonly property string iPrev: ""
    readonly property string iDelete: ""
    readonly property string iFolder: ""
    readonly property string iSettings: ""
    readonly property string iEdit: ""
    readonly property string iNext: ""
    readonly property string iHeart: ""
    readonly property string iHeartFill: ""
    readonly property string iDislike: ""
    readonly property string iVolume: ""
    readonly property string iMute: ""
    readonly property string iSearch: ""
    readonly property string iRefresh: ""
    readonly property string iAdd: ""
    readonly property string iClose: ""
    readonly property string iChevronDown: ""
    readonly property string iChevronUp: ""
    readonly property string iPanel: ""
    readonly property string iLogout: ""
    readonly property string iWave: ""
    readonly property string iLibrary: ""
    readonly property string iCatalogue: ""
    readonly property string iBlock: ""
    readonly property string iMinimize: ""
    readonly property string iMaximize: ""
    readonly property string iRestore: ""
    readonly property string iWinClose: ""

    function alpha(baseColor, amount) {
        return Qt.rgba(baseColor.r, baseColor.g, baseColor.b, amount)
    }
}
