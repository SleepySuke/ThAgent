package com.suke.ai;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * @author 自然醒
 * @version 1.0
 */
@SpringBootApplication
public class SSAHelloWorldApplication {
    public static void main(String[] args) {
        SpringApplication.run(SSAHelloWorldApplication.class, args);
    }
}
