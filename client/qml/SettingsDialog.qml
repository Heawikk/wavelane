import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    Settings: how the app looks, and its integrations with the rest of the
    desktop (what Windows shows in its media panel, what Discord shows on the
    profile).
*/
Popup {
    id: root

    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    dim: true
    focus: true
    padding: 0
    width: Math.min(560, (parent ? parent.width : 560) - 24)
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    Overlay.modal: Rectangle { color: Theme.alpha("#000000", 0.6) }

    background: Rectangle {
        color: Theme.bar
        border.color: Theme.borderStrong
        border.width: 1
    }

    contentItem: ColumnLayout {
        spacing: 0

        SectionHeader {
            Layout.fillWidth: true
            title: qsTr("Настройки")

            IconButton {
                glyph: Theme.iClose
                onClicked: root.close()
            }
        }

        // The sections can outgrow a small window, so they scroll.
        Flickable {
            id: scroller

            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(sections.implicitHeight,
                                             Math.max(200, (root.parent ? root.parent.height : 700) - 150))
            contentWidth: width
            contentHeight: sections.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            ScrollBar.vertical: FlatScrollBar {}

            ColumnLayout {
                id: sections
                width: scroller.width
                spacing: 0

            // --- Account ---
            RowLayout {
                visible: auth.signedIn
                Layout.fillWidth: true
                Layout.margins: 18
                Layout.bottomMargin: 6
                spacing: 12

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2

                    Mono {
                        text: qsTr("Аккаунт")
                        color: Theme.text
                        font.weight: Font.DemiBold
                    }
                    Text {
                        Layout.fillWidth: true
                        text: (auth.displayName || auth.username || qsTr("Вы вошли")) + (auth.isAdmin ? " · " + qsTr("администратор") : "")
                        color: Theme.muted
                        font.family: Theme.sans
                        font.pixelSize: Theme.fontSmall
                        elide: Text.ElideRight
                    }
                }
                FlatButton {
                    text: qsTr("Выйти")
                    danger: true
                    onClicked: {
                        root.close()
                        auth.signOut()
                    }
                }
            }

            Rectangle {
                visible: auth.signedIn
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                Layout.topMargin: 12
                color: Theme.border
            }

            // --- Looks ---
            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 18
                Layout.bottomMargin: 6
                spacing: 12

                Mono {
                    text: qsTr("Персонализация")
                    color: Theme.text
                    font.weight: Font.DemiBold
                }

                RowLayout {
                    Layout.fillWidth: true

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Text {
                            text: qsTr("Светящиеся пятна")
                            color: Theme.text
                            font.family: Theme.sans
                            font.pixelSize: Theme.fontBody
                        }
                        Text {
                            Layout.fillWidth: true
                            text: qsTr("Фон страницы «Моя волна». Если выключить, видеокарта не рисует его вовсе.")
                            color: Theme.faint
                            font.family: Theme.sans
                            font.pixelSize: Theme.fontSmall
                            wrapMode: Text.WordWrap
                        }
                    }
                    Segmented {
                        Layout.alignment: Qt.AlignTop
                        options: [
                            { value: "on",  label: qsTr("Включены") },
                            { value: "off", label: qsTr("Выключены") }
                        ]
                        current: app.blobsEnabled ? "on" : "off"
                        onPicked: function(value) { app.blobsEnabled = value === "on" }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text {
                        text: qsTr("Визуализатор")
                        color: Theme.text
                        font.family: Theme.sans
                        font.pixelSize: Theme.fontBody
                    }
                    Segmented {
                        Layout.fillWidth: true
                        stretch: true
                        options: [
                            { value: "bars", label: qsTr("Столбики") },
                            { value: "wave", label: qsTr("Волна") },
                            { value: "dots", label: qsTr("Точки") },
                            { value: "ring", label: qsTr("Кольцо") },
                            { value: "off",  label: qsTr("Выкл") }
                        ]
                        current: app.visualizerStyle
                        onPicked: function(value) { app.visualizerStyle = value }
                    }
                }
            }

            Rectangle {
                visible: Qt.platform.os === "windows"
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                Layout.topMargin: 12
                color: Theme.border
            }

            // --- Windows ---
            ColumnLayout {
                visible: Qt.platform.os === "windows"
                Layout.fillWidth: true
                Layout.margins: 18
                Layout.bottomMargin: 6
                spacing: 6

                Mono {
                    text: qsTr("Панель мультимедиа Windows")
                    color: Theme.text
                    font.weight: Font.DemiBold
                }
                Row {
                    spacing: 8
                    Rectangle {
                        width: 6
                        height: 6
                        radius: 3
                        color: media.active ? Theme.positive : Theme.faint
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Mono {
                        text: media.active ? qsTr("Подключена") : qsTr("Недоступна")
                        color: Theme.muted
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Обложка, название и исполнитель показываются в панели громкости, на экране "
                               + "блокировки и в быстрых настройках. Медиа-клавиши клавиатуры и наушников "
                               + "управляют воспроизведением.")
                    color: Theme.faint
                    font.family: Theme.sans
                    font.pixelSize: Theme.fontSmall
                    wrapMode: Text.WordWrap
                    lineHeight: 1.2
                }
            }

            Rectangle {
                visible: Qt.platform.os === "windows"
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                Layout.topMargin: 12
                color: Theme.border
            }

            // --- Discord ---
            ColumnLayout {
                visible: Qt.platform.os === "windows"
                Layout.fillWidth: true
                Layout.margins: 18
                spacing: 12

                RowLayout {
                    Layout.fillWidth: true

                    Mono {
                        text: qsTr("Discord")
                        color: Theme.text
                        font.weight: Font.DemiBold
                    }
                    Item { Layout.fillWidth: true }
                    Segmented {
                        options: [
                            { value: "on",  label: qsTr("Включено") },
                            { value: "off", label: qsTr("Выключено") }
                        ]
                        current: app.discordEnabled ? "on" : "off"
                        onPicked: function(value) { app.discordEnabled = value === "on" }
                    }
                }

                Row {
                    spacing: 8
                    Rectangle {
                        width: 6
                        height: 6
                        radius: 3
                        color: discord.connected ? Theme.positive : Theme.faint
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Mono {
                        text: discord.status
                        color: discord.connected ? Theme.text : Theme.muted
                        font.capitalization: Font.MixedCase
                        font.letterSpacing: 0.2
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: qsTr("В профиле Discord показывается «Слушает Wavelane»: название и исполнитель "
                               + "трека, обложка и полоса прогресса. Когда Wavelane закрывается, "
                               + "статус убирается.")
                    color: Theme.faint
                    font.family: Theme.sans
                    font.pixelSize: Theme.fontSmall
                    wrapMode: Text.WordWrap
                    lineHeight: 1.2
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                Layout.topMargin: 12
                color: Theme.border
            }

            // --- Version and updates ---
            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 18
                spacing: 12

                RowLayout {
                    Layout.fillWidth: true

                    Mono {
                        text: qsTr("Версия")
                        color: Theme.text
                        font.weight: Font.DemiBold
                    }
                    Item { Layout.fillWidth: true }
                    Mono {
                        text: appVersion
                        color: Theme.muted
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    Text {
                        id: statusText
                        Layout.fillWidth: true
                        visible: text !== ""
                        text: updates.state === "current" ? qsTr("Актуальная версия")
                              : updates.state === "available" ? (updates.message !== "" ? updates.message
                                                                 : qsTr("Доступна версия %1").arg(updates.latestVersion))
                              : updates.state === "downloading" ? qsTr("Загрузка… %1%").arg(Math.round(updates.progress * 100))
                              : updates.state === "installing" ? qsTr("Устанавливаю, приложение перезапустится…")
                              : updates.state === "error" ? updates.message
                              : ""
                        color: updates.state === "current" ? Theme.positive
                               : updates.state === "error" ? Theme.negative
                               : Theme.muted
                        font.family: Theme.sans
                        font.pixelSize: Theme.fontSmall
                        wrapMode: Text.WordWrap
                    }
                    Item {
                        Layout.fillWidth: true
                        visible: !statusText.visible
                    }

                    FlatButton {
                        visible: updates.state === "available"
                        primary: true
                        text: qsTr("Обновить")
                        onClicked: updates.install()
                    }
                    FlatButton {
                        visible: updates.state !== "available"
                        text: updates.state === "checking" ? qsTr("Проверка…") : qsTr("Проверить обновление")
                        enabledWhen: updates.state !== "checking" && updates.state !== "downloading"
                                     && updates.state !== "installing"
                        onClicked: updates.check()
                    }
                }
            }
            }
        }
    }
}
