import QtQuick
import QtQuick.Layouts
import Wavelane

/*!
    The top bar, which is also the window's title bar.

    Everything that is not a control drags the window and double-clicking it
    maximises, exactly like the native bar it replaces. While signed out only
    the brand and the window buttons are shown.
*/
Rectangle {
    id: root

    required property var window
    readonly property bool signedIn: auth.signedIn
    readonly property bool maximized: window.visibility === Window.Maximized
    readonly property bool wavePlaying: wave.started && player.hasTrack
                                        && player.context === "wave"

    color: Theme.bar

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

    readonly property string stateText: player.buffering ? qsTr("Буферизация")
                                        : player.playing ? qsTr("Играет")
                                        : player.hasTrack ? qsTr("Пауза")
                                        : qsTr("Остановлено")

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
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // --- brand ---
        Row {
            Layout.leftMargin: 14
            Layout.rightMargin: 16
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

        Rectangle {
            visible: root.signedIn
            Layout.preferredWidth: 1
            Layout.fillHeight: true
            color: Theme.border
        }

        // --- what is playing ---
        ColumnLayout {
            visible: root.signedIn
            Layout.preferredWidth: 200
            Layout.maximumWidth: 200
            Layout.leftMargin: 16
            spacing: 1

            Row {
                spacing: 7

                Rectangle {
                    width: 6
                    height: 6
                    radius: 3
                    color: player.playing ? Theme.positive : Theme.faint
                    anchors.verticalCenter: parent.verticalCenter
                }
                Mono {
                    text: root.stateText
                    font.pixelSize: 10
                    font.weight: Font.DemiBold
                    color: player.playing ? Theme.text : Theme.muted
                }
            }

            Text {
                Layout.fillWidth: true
                text: player.hasTrack ? player.currentTrack.title + " — "
                                        + player.currentTrack.artistName
                                      : qsTr("Выберите трек")
                color: player.hasTrack ? Theme.muted : Theme.faint
                font.family: Theme.sans
                font.pixelSize: Theme.fontSmall
                elide: Text.ElideRight
            }
        }

        Rectangle {
            visible: root.signedIn
            Layout.preferredWidth: 1
            Layout.fillHeight: true
            Layout.leftMargin: 14
            color: Theme.border
        }

        // --- the three dials of the wave ---
        Segmented {
            visible: root.signedIn
            Layout.leftMargin: 14
            options: root.characterOptions
            current: wave.character
            onPicked: function(value) { wave.setCharacter(value) }
        }

        FlatCombo {
            visible: root.signedIn
            Layout.leftMargin: 10
            implicitWidth: 172
            options: root.moodOptions
            current: wave.mood
            onPicked: function(value) { wave.setMood(value) }
        }

        FlatCombo {
            visible: root.signedIn
            Layout.leftMargin: 6
            implicitWidth: 132
            options: root.languageOptions
            current: wave.language
            onPicked: function(value) { wave.setLanguage(value) }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
        }

        FlatButton {
            visible: root.signedIn
            Layout.rightMargin: 12
            primary: true
            glyph: root.wavePlaying ? Theme.iNext : Theme.iPlay
            text: root.wavePlaying ? qsTr("Дальше") : qsTr("Слушать волну")
            enabledWhen: !wave.loading
            onClicked: root.wavePlaying ? wave.playNext() : wave.start()
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
