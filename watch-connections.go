package main

import (
	"database/sql"
	"fmt"
	"log"
	"time"

	_ "github.com/go-sql-driver/mysql"
)

func main() {
	db, err := sql.Open("mysql", "root@tcp(127.0.0.1:3306)/")
	if err != nil {
		log.Fatal(err)
	}
	defer db.Close()

	fmt.Println("Watching MySQL Connection Counts (Ctrl+C to stop)...")
	for {
		var name, value string
		err := db.QueryRow("SHOW GLOBAL STATUS LIKE 'Threads_connected'").Scan(&name, &value)
		if err != nil {
			fmt.Printf("Error: %v\n", err)
		} else {
			fmt.Printf("[%s] %s: %s\n", time.Now().Format("15:04:05"), name, value)
		}
		time.Sleep(1 * time.Second)
	}
}
