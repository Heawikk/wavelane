import QtQuick
import QtQuick.Layouts
import Wavelane

/*!
    The strip along the top of the window, which is also its title bar.

    Signed out it carries the brand; signed in the brand lives in the sidebar,
    so the bar is just the drag area and window buttons — plus, on the wave
    page only, the dials that steer the wave.
*/
Rectangle {
    id: root

    required property var window
    property string page: "wave"

    readonly property bool signedIn: auth.signedIn
    readonly property bool maximized: window.visibility === Window.Maximized
    readonly property bool showDials: signedIn && page === "wave"

    color: signedIn ? "transparent" : Theme.bar

    readonly property var characterOptions: [
        { value: "any",        label: qsTr("Любой") },
        { value: "favourite",  label: qsTr("Любимое") },
        { value: "unfamiliar", label: qsTr("Новое") },
        { value: "popular",    label: qsTr("Хиты") }
    ]
    readonly property var moodOptions: [
        { value: "any",       label: qsTr("Любое настроение") },
        { value: "energetic", label: qsTr("Бодрое") },
        { value: "party",     label: qsTr("Танцевальное") },
        { value: "chill",     label: qsTr("Спокойное") },
        { value: "calm",      label: qsTr("Тихое") },
        { value: "focus",     label: qsTr("Для сосредоточения") },
        { value: "sad",       label: qsTr("Грустное") }
    ]
    readonly property var languageOptions: [
        { value: "any",          label: qsTr("Любой язык") },
        { value: "russian",      label: qsTr("Русский") },
        { value: "foreign",      label: qsTr("Иностранный") },
        { value: "instrumental", label: qsTr("Без слов") }
    ]
    readonly property var diversityOptions: [
        { value: "0.1", label: qsTr("Разнообразие 10%") },
        { value: "0.3", label: qsTr("Разнообразие 30%") },
        { value: "0.6", label: qsTr("Разнообразие 60%") },
        { value: "0.9", label: qsTr("Разнообразие 90%") }
    ]

    //! The stored diversity is a free number; show the nearest preset.
    function nearestDiversity() {
        let best = diversityOptions[0].value
        let distance = 10
        for (let i = 0; i < diversityOptions.length; ++i) {
            const gap = Math.abs(parseFloat(diversityOptions[i].value) - wave.diversity)
            if (gap < distance) {
                distance = gap
                best = diversityOptions[i].value
            }
        }
        return best
    }

    // --- drag the window by any empty part of the bar -----------------------
    Item {
        anchors.fill: parent

        DragHandler {
            target: null
            onActiveChanged: if (active) root.window.startSystemMove()
        }
        TapHandler {
            onDoubleTapped: root.maximized ? root.window.showNormal()
                                           : root.window.showMaximized()
        }
    }

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        color: Theme.border
        visible: !root.signedIn
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // brand, only before sign-in
        Row {
            visible: !root.signedIn
            Layout.leftMargin: 14
            spacing: 10

            Rectangle {
                width: 24
                height: 24
                color: Theme.accent
                anchors.verticalCenter: parent.verticalCenter

                Canvas {
                    anchors.fill: parent
                    onPaint: {
                        const ctx = getContext("2d")
                        ctx.reset()
                        ctx.strokeStyle = "white"
                        ctx.lineWidth = 1.6
                        ctx.lineCap = "round"
                        for (let i = 0; i < 3; ++i) {
                            const y = 8 + i * 4
                            ctx.beginPath()
                            ctx.moveTo(4, y)
                            ctx.bezierCurveTo(8, y - 4, 14, y + 4, 20, y)
                            ctx.stroke()
                        }
                    }
                }
            }

            Text {
                text: "Wavelane"
                color: Theme.text
                font.family: Theme.sans
                font.pixelSize: 16
                font.weight: Font.Bold
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
        }

        // --- the dials of the wave ---
        Segmented {
            visible: root.showDials
            Layout.alignment: Qt.AlignVCenter
            options: root.characterOptions
            current: wave.character
            onPicked: function(value) { wave.setCharacter(value) }
        }

        FlatCombo {
            visible: root.showDials
            Layout.alignment: Qt.AlignVCenter
            Layout.leftMargin: 8
            implicitWidth: 172
            options: root.moodOptions
            current: wave.mood
            onPicked: function(value) { wave.setMood(value) }
        }

        FlatCombo {
            visible: root.showDials
            Layout.alignment: Qt.AlignVCenter
            Layout.leftMargin: 6
            implicitWidth: 132
            options: root.languageOptions
            current: wave.language
            onPicked: function(value) { wave.setLanguage(value) }
        }

        FlatCombo {
            visible: root.showDials
            Layout.alignment: Qt.AlignVCenter
            Layout.leftMargin: 6
            Layout.rightMargin: 14
            implicitWidth: 168
            options: root.diversityOptions
            current: root.nearestDiversity()
            onPicked: function(value) { wave.setDiversity(parseFloat(value)) }
        }

        // --- window controls ---
        WindowButton {
            Layout.alignment: Qt.AlignTop
            glyph: Theme.iMinimize
            onClicked: root.window.showMinimized()
        }
        WindowButton {
            Layout.alignment: Qt.AlignTop
            glyph: root.maximized ? Theme.iRestore : Theme.iMaximize
            onClicked: root.maximized ? root.window.showNormal() : root.window.showMaximized()
        }
        WindowButton {
            Layout.alignment: Qt.AlignTop
            glyph: Theme.iWinClose
            danger: true
            onClicked: root.window.close()
        }
    }
}
