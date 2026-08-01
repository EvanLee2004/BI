# managed by publish_kanban blue-green — default primary
upstream kanban_api {
    server 127.0.0.1:8018;
    keepalive 8;
}
