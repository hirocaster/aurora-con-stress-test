package main

import (
	"log"
	"net"
	"github.com/go-mysql-org/go-mysql/mysql"
	"github.com/go-mysql-org/go-mysql/server"
)

type dummyHandler struct {
	server.EmptyHandler
}

func (h *dummyHandler) HandleQuery(query string) (*mysql.Result, error) {
	// Return empty result set
	r, _ := mysql.BuildSimpleTextResultset([]string{"1"}, [][]interface{}{{"1"}})
	return &mysql.Result{Status: 0, InsertId: 0, AffectedRows: 0, Resultset: r}, nil
}

func main() {
	l, err := net.Listen("tcp", "127.0.0.1:3306")
	if err != nil {
		log.Fatal(err)
	}

	for {
		c, err := l.Accept()
		if err != nil {
			log.Print(err)
			continue
		}

		go func(conn net.Conn) {
			svr, err := server.NewServer("5.7.0", mysql.DEFAULT_COLLATION_ID, mysql.AUTH_NATIVE_PASSWORD, nil, nil)
			if err != nil {
				conn.Close()
				return
			}
			
			// Custom auth
			svr.SetAuth(&server.InMemoryProvider{})

			// create connection
			c := server.NewCustomizedConn(conn, svr, &server.InMemoryProvider{}, &dummyHandler{})
			
			for {
				if err := c.HandleCommand(); err != nil {
					return
				}
			}
		}(c)
	}
}
