package main

import (
	"database/sql"
	"fmt"
	"log"

	_ "github.com/go-sql-driver/mysql"
)

func main() {
	db, err := sql.Open("mysql", "root@tcp(127.0.0.1:3306)/")
	if err != nil {
		log.Fatal(err)
	}
	defer db.Close()

	queries := []string{
		"FLUSH PRIVILEGES;",
		"CREATE DATABASE IF NOT EXISTS mydb;",
		"CREATE USER IF NOT EXISTS 'admin'@'%' IDENTIFIED BY 'secret';",
		"GRANT ALL PRIVILEGES ON mydb.* TO 'admin'@'%';",
		"FLUSH PRIVILEGES;",
	}
	for _, q := range queries {
		_, err = db.Exec(q)
		if err != nil {
			fmt.Printf("Error executing %s: %v\n", q, err)
		} else {
			fmt.Printf("Success: %s\n", q)
		}
	}
}
