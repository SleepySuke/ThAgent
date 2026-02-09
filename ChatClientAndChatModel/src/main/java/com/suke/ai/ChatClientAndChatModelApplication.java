package com.suke.ai;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.transaction.annotation.EnableTransactionManagement;

/**
 * @author 自然醒
 * @version 1.0
 */
@SpringBootApplication
@MapperScan("com.suke.ai.mapper")
//@EnableTransactionManagement
public class ChatClientAndChatModelApplication {
    public static void main(String[] args) {
        SpringApplication.run(ChatClientAndChatModelApplication.class, args);
    }
}
