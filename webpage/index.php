<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN">
<html>

<head>
  <title>A Query</title>
</head>

<body>

<h1>Power Graphs</h1>

<?php
include("graph.php");

$handle = opendir('graphs');
while (false !== ($f = readdir($handle))) {
    if ($f != '.' && $f != '..') {
        echo '<p><img src="graphs/'. $f .'"></p>';
    }
}
?>

</body>
</html>
