// Environment smoke only. Matching official JDBC driver stays outside the repository.
import java.sql.*;
import java.util.Properties;

class ZetarisSmoke {
    public static void main(String[] args) {
        try {
            String driver = System.getenv("ZETARIS_JDBC_DRIVER");
            if (driver != null && !driver.isBlank()) Class.forName(driver);
            Properties credentials = new Properties();
            credentials.setProperty("user", System.getenv("ZETARIS_USERNAME"));
            credentials.setProperty("password", System.getenv("ZETARIS_PASSWORD"));
            DriverManager.setLoginTimeout(15);
            try (Connection connection = DriverManager.getConnection(System.getenv("ZETARIS_JDBC_URL"), credentials);
                 Statement statement = connection.createStatement();
                 ResultSet rows = statement.executeQuery(System.getenv("ZETARIS_DATASET_SQL"))) {
                if (!rows.next() || rows.getMetaData().getColumnCount() < 1) {
                    System.out.println("FAIL no dataset rows returned");
                    System.exit(1);
                }
                System.out.println("PASS authenticated dataset SELECT returned a row; values withheld");
            }
        } catch (Exception error) {
            // JDBC error messages can echo URLs, queries and credentials.
            System.out.println("FAIL JDBC dataset query; exception details withheld");
            System.exit(1);
        }
    }
}
