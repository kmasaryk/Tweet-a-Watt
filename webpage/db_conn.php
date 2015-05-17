<?php

$DBServer = '3jane';
$DBUser   = 'power';
$DBPass   = 'power';
$DBName   = 'power';

$conn = new mysqli($DBServer, $DBUser, $DBPass, $DBName);

if ($conn->connect_error) {
    trigger_error('DB connection failed: ' . $conn->connect_error,
                  E_USER_ERROR);
}

?>