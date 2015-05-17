<?php

require_once("../pChart/class/pData.class.php");
require_once("../pChart/class/pDraw.class.php");
require_once("../pChart/class/pImage.class.php");
require_once("db_conn.php");

// Picture size
$PIC_W = 700;
$PIC_H = 230;

// Graph area size
$GA_X_START = 60;
$GA_X_END = $PIC_W - $GA_X_START;
$GA_Y_START = 40;
$GA_Y_END = $PIC_H - $GA_Y_START;

function create_graph($dev_id) {
    global $conn, $PIC_W, $PIC_H, $GA_X_START, $GA_X_END, $GA_Y_START,
        $GA_Y_END;

    $sql = 'SELECT d.name, d.description, dc.watthr, dc.time ' .
           'FROM data_collect AS dc ' .
           'JOIN devices AS d ON (dc.device_id = d.id) ' .
           'WHERE device_id = ' . $dev_id;

    $rs = $conn->query($sql);

    if ($rs === false) {
        trigger_error("Bad query: $sql Error: $conn->error",
                      E_USER_ERROR);
    }

    $myData = new pData();

    $rs->data_seek(0);
    while ($row = $rs->fetch_assoc()) {
        $myData->addPoints($row['watthr']);
        $myData->addPoints(VOID, "time");
    }
    $myData->setAxisName(0, "Watt Hours");
    $myData->setAbscissa("time");

    $rs->data_seek(0);
    $row = $rs->fetch_assoc();
    $start_time = $row['time'];
    $title = "{$row['name']} ({$row['description']})";

    $rs->data_seek($rs->num_rows - 1);
    $end_time = $rs->fetch_assoc()['time'];
    $myData->setAbscissaName("Time [$start_time - $end_time]");

    $myPicture = new pImage($PIC_W, $PIC_H, $myData);
    $myPicture->setGraphArea($GA_X_START, $GA_Y_START, $GA_X_END,
                             $GA_Y_END);

    $mid_x = $PIC_W / 2;
    $myPicture->drawText($mid_x, 20, $title,
                         array("FontName" => "../pChart/fonts/calibri.ttf",
                               "FontSize" => 16,
                               "Align" => TEXT_ALIGN_BOTTOMMIDDLE));

    $myPicture->setFontProperties(array("FontName" => "../pChart/fonts/verdana.ttf",
                                        "FontSize" => 10));
    $myPicture->drawScale();
    $myPicture->drawSplineChart();
    $myPicture->render("graphs/{$row['name']}.png");
}

$sql = 'SELECT device_id '.
       'FROM data_collect '.
       'GROUP BY device_id '.
       'HAVING COUNT(*) > 5';

$rs = $conn->query($sql);

if ($rs === false) {
    trigger_error("Bad query: $sql Error: $conn->error", E_USER_ERROR);
}

while ($row = $rs->fetch_assoc()) {
    create_graph($row['device_id']);
}

?>